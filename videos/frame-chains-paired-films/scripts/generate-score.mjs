import { createWriteStream } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const output = resolve(process.argv[2] || "assets/bgm/track.wav");
const duration = Number(process.argv[3] || 105.344);
const sampleRate = 48_000;
const channels = 2;
const bitsPerSample = 16;
const frameCount = Math.round(duration * sampleRate);
const dataBytes = frameCount * channels * (bitsPerSample / 8);
const beat = 60 / 96;
const chordSpan = beat * 8;

const chords = [
  [146.83, 174.61, 220.0],
  [116.54, 146.83, 174.61],
  [174.61, 220.0, 261.63],
  [130.81, 164.81, 196.0],
];

function smoothstep(value) {
  const x = Math.max(0, Math.min(1, value));
  return x * x * (3 - 2 * x);
}

function hashNoise(index) {
  let value = (index ^ 0x9e3779b9) >>> 0;
  value = Math.imul(value ^ (value >>> 16), 0x21f0aaad);
  value = Math.imul(value ^ (value >>> 15), 0x735a2d97);
  return ((value ^ (value >>> 15)) >>> 0) / 0xffffffff * 2 - 1;
}

function padAt(frequencies, time, phaseOffset) {
  return frequencies.reduce((sum, frequency, index) => {
    const phase = phaseOffset + index * 0.61;
    return sum
      + Math.sin(2 * Math.PI * frequency * time + phase) * 0.24
      + Math.sin(2 * Math.PI * frequency * 2 * time + phase * 1.7) * 0.05;
  }, 0) / frequencies.length;
}

function sampleAt(time, channel) {
  const chordPosition = time / chordSpan;
  const chordIndex = Math.floor(chordPosition) % chords.length;
  const nextChordIndex = (chordIndex + 1) % chords.length;
  const withinChord = time % chordSpan;
  const blend = smoothstep((withinChord - (chordSpan - 0.9)) / 0.9);
  const phaseOffset = channel === 0 ? 0 : 0.17;
  const pad = padAt(chords[chordIndex], time, phaseOffset) * (1 - blend)
    + padAt(chords[nextChordIndex], time, phaseOffset) * blend;

  const beatPhase = (time % beat) / beat;
  const pulseEnvelope = Math.exp(-beatPhase * 7);
  const pulseFrequency = chordIndex === 1 ? 49 : 55;
  const pulse = (
    Math.sin(2 * Math.PI * pulseFrequency * time)
    + Math.sin(2 * Math.PI * pulseFrequency * 2 * time) * 0.25
  ) * pulseEnvelope;

  const halfBeat = beat / 2;
  const tickPhase = (time % halfBeat) / halfBeat;
  const tickEnvelope = Math.exp(-tickPhase * 24);
  const index = Math.floor(time * sampleRate);
  const noise = hashNoise(index) - hashNoise(Math.max(0, index - 1));
  const tick = noise * tickEnvelope;

  const barPhase = (time % (beat * 4)) / (beat * 4);
  const pluckEnvelope = Math.exp(-barPhase * 11);
  const pluckFrequency = chords[chordIndex][2] * 2;
  const pluck = Math.sin(2 * Math.PI * pluckFrequency * time + channel * 0.3)
    * pluckEnvelope;

  const progress = time / duration;
  const energy = 0.72 + smoothstep((progress - 0.2) / 0.7) * 0.28;
  const fadeIn = smoothstep(time / 1.8);
  const fadeOut = smoothstep((duration - time) / 3.2);
  const stereoDrift = Math.sin(2 * Math.PI * 0.035 * time + channel * Math.PI)
    * 0.012;

  return (
    pad * 0.42
    + pulse * 0.085 * energy
    + tick * 0.008 * energy
    + pluck * 0.025
    + stereoDrift
  ) * fadeIn * fadeOut;
}

function wavHeader() {
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + dataBytes, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(channels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * channels * bitsPerSample / 8, 28);
  header.writeUInt16LE(channels * bitsPerSample / 8, 32);
  header.writeUInt16LE(bitsPerSample, 34);
  header.write("data", 36);
  header.writeUInt32LE(dataBytes, 40);
  return header;
}

await mkdir(dirname(output), { recursive: true });
const stream = createWriteStream(output);
stream.write(wavHeader());

const chunkFrames = 4096;
for (let start = 0; start < frameCount; start += chunkFrames) {
  const count = Math.min(chunkFrames, frameCount - start);
  const chunk = Buffer.allocUnsafe(count * channels * 2);
  for (let frame = 0; frame < count; frame += 1) {
    const time = (start + frame) / sampleRate;
    for (let channel = 0; channel < channels; channel += 1) {
      const value = Math.max(-1, Math.min(1, sampleAt(time, channel)));
      chunk.writeInt16LE(Math.round(value * 32767), (frame * channels + channel) * 2);
    }
  }
  if (!stream.write(chunk)) {
    await new Promise((resolveDrain) => stream.once("drain", resolveDrain));
  }
}

await new Promise((resolveFinish, reject) => {
  stream.end(resolveFinish);
  stream.on("error", reject);
});

console.log(`generated ${output} (${duration.toFixed(3)}s, ${sampleRate} Hz stereo)`);
