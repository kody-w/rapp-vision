const byId = id => document.getElementById(id);
const audio = byId("narration");
const configUrl = new URL("../context/intro-v2.json", import.meta.url);
let chapters = [];
let initialChapter = 0;
let chapter = 0;
let generation = 0;
let status = "loading";

function announce(message, error = false) {
  byId("status").textContent = message;
  byId("status").dataset.error = String(error);
}

function select(index) {
  if (!Number.isInteger(index) || index < 0 || index >= chapters.length) {
    throw new RangeError("The requested introduction chapter does not exist.");
  }
  generation += 1;
  status = "ready";
  audio.pause();
  audio.currentTime = 0;
  chapter = index;
  const item = chapters[chapter];
  audio.src = new URL(item.audio.src, configUrl).href;
  audio.load();
  byId("heading").textContent = item.title;
  byId("part").textContent = `Part ${chapter + 1} of ${chapters.length}`;
  byId("points").replaceChildren(...item.copy.map(text => {
    const point = document.createElement("li");
    point.textContent = text;
    return point;
  }));
  byId("transcript-text").textContent = item.narration;
  byId("transcript").open = false;
  byId("hear").disabled = false;
  byId("pause").disabled = true;
  byId("previous").disabled = chapter === 0;
  byId("next").disabled = chapter === chapters.length - 1;
  byId("reset").disabled = false;
  announce("Hear the explanation, or read the cards at your own pace.");
}

async function play() {
  const requestedGeneration = generation;
  try {
    await audio.play();
    if (requestedGeneration !== generation) return;
    status = "playing";
    byId("pause").disabled = false;
    announce("Narration playing.");
  } catch (error) {
    if (requestedGeneration !== generation) return;
    status = "blocked";
    byId("pause").disabled = true;
    announce(
      error instanceof DOMException && error.name === "NotAllowedError"
        ? "Your browser needs a direct tap on Hear the explanation to start narration."
        : "Narration could not play. The complete explanation remains available below.",
      true,
    );
    console.error("Introduction narration could not play.", error);
    if (!(error instanceof DOMException)) throw error;
  }
}

byId("hear").addEventListener("click", play);
byId("pause").addEventListener("click", () => audio.pause());
byId("previous").addEventListener("click", () => select(chapter - 1));
byId("next").addEventListener("click", () => select(chapter + 1));
byId("reset").addEventListener("click", () => select(initialChapter));

audio.addEventListener("pause", () => {
  if (status !== "playing") return;
  status = "paused";
  byId("pause").disabled = true;
  announce("Narration paused. Hear the explanation resumes it.");
});
audio.addEventListener("ended", () => {
  if (!audio.ended) return;
  status = "complete";
  byId("pause").disabled = true;
  announce(chapter === chapters.length - 1
    ? "Now watch for an allowed change, a refusal, and the accepted state staying intact."
    : "This explanation is complete. Continue to the next part.");
});
audio.addEventListener("error", () => {
  status = "blocked";
  byId("pause").disabled = true;
  announce("The narration file could not be loaded. You can still read the full explanation.", true);
  console.error("The introduction narration resource is unavailable.");
});

window.frameChainsIntro = Object.freeze({
  snapshot: () => ({
    version: 1,
    chapter,
    status,
    timeMs: Math.round(audio.currentTime * 1000),
    transcriptOpen: byId("transcript").open,
  }),
});

async function initialize() {
  const response = await fetch(configUrl);
  if (!response.ok) throw new Error(`Introduction data could not load (${response.status}).`);
  const data = await response.json();
  if (data.schema !== "rapp-vision-topic-intro/1" || !Array.isArray(data.chapters) || !data.chapters.length) {
    throw new Error("The introduction has an unsupported data format.");
  }
  for (const item of data.chapters) {
    if (
      typeof item.title !== "string" || !item.title.trim()
      || typeof item.narration !== "string" || !item.narration.trim()
      || !Array.isArray(item.copy) || !item.copy.length
      || item.copy.some(text => typeof text !== "string" || !text.trim())
      || !item.audio || !/^audio\/intro-\d{2}\.wav$/.test(item.audio.src)
      || !Number.isInteger(item.audio.duration_ms) || item.audio.duration_ms <= 0
    ) throw new Error("An introduction chapter is incomplete.");
  }
  chapters = data.chapters;
  const requested = new URLSearchParams(location.search).get("chapter");
  if (requested !== null && !/^\d+$/.test(requested)) throw new Error("The chapter number is invalid.");
  initialChapter = requested === null ? 0 : Number(requested);
  select(initialChapter);
  document.documentElement.dataset.ready = "true";
}

initialize().catch(error => {
  status = "blocked";
  announce(error.message, true);
  console.error("Frame Chains introduction could not initialize.", error);
});
