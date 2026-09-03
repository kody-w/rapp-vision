# Candidate frame 0003-03 · Island Herd Threshold

**Will the Island Herd Hold?** answers commission
`explore-ecosystem-threshold` with one prediction-first paired publication.
The 22-second 960×540 film and standalone live lab use the same seeded model,
the same two canonical traces, and the same exact reset.

## Editorial flow

The opening does not reveal a graph. It asks the viewer to predict whether the
herd stays in the 80–120 band or collapses below 10.

1. With seed **31415** and grazing **0.24**, predict “stays in band.”
2. Reveal all 600 ticks and inspect the result: population **112**, resources
   **141.688**, and no collapse crossing.
3. Change grazing to **0.60**. The old trace is cleared and a new prediction is
   required.
4. Revise the prediction to “collapses,” select 2× viewing speed, and reveal
   the same model. Population first falls below 10 at tick **134** and ends at
   **8** on tick 600.
5. Activate **Reset ecosystem**. Seed 31415, grazing 0.24, speed 1×,
   population 104, resources 146, tick zero, no prediction, and an empty trace
   return exactly.

The live range accepts every hundredth from 0.00 through 0.75. Either
prediction can be chosen for any rate. The committed evidence remains fixed to
0.24 and 0.60 so review does not depend on an arbitrary interactive choice.

## Seeded model

The implementation uses integer thousandths so Python and JavaScript take the
same steps without rounding drift.

At each tick:

1. `xorshift32` advances once from the selected seed. Its low ten bits produce
   a small weather change between -0.275 and +0.274 resource units.
2. Grass regrows by four percent of the current gap to 180. Grazing removes
   `6.4 × grazing rate` resource units, then the weather change is added.
3. Grass at 90 or lower supports a herd of 8; grass at 120 or higher supports
   112. Between 90 and 120, the recovered share is squared before scaling from
   8 to 112. This makes low grass recover herd support slowly and creates the
   documented threshold without a hidden branch for either fixture.
4. The population moves 3.5 percent of the gap toward that supported herd
   size. While a nonzero gap remains, the smallest move is one thousandth.

The seed affects every grass update. Grazing is the only canonical parameter
change. `render.py`, the browser app, `exports/fixture-series.json`, and
`evidence.json` independently expose the rules and all 601 points per fixture.

## Bundle

| Path | Purpose |
| --- | --- |
| `apps/ecosystem-island-threshold.html` | Offline single-file prediction lab, model, chart, full-series export, and `window.islandLab.snapshot()` |
| `render.py` | Standard-library model, RGB renderer, lossless-master writer, thumbnail/evidence/delivery generator |
| `masters/ecosystem-island-threshold.mkv` | 22-second single-threaded FFV1 lossless master |
| `media/ecosystem-island-threshold.mp4` | Compiler-produced H.264/yuv420p/BT.709 delivery |
| `media/ecosystem-island-threshold.webm` | Compiler-produced VP9/yuv420p/BT.709 delivery |
| `channel.production.json` | Production authoring source and semantic live replay |
| `channel.json` | Compiler-produced paired channel |
| `thumbs/ecosystem-island-threshold.svg` | Original self-contained thumbnail |
| `exports/fixture-series.json` | Every tick, population, resources, support, weather, and random state for both fixtures |
| `snapshots/canonical-states.json` | Opening, stable, collapse, and exact-reset window summaries |
| `evidence.json` | Model, full compact series, final values, crossing proof, live checkpoints, rights/privacy, and SHA-256 bindings |
| `delivery.json` | SHA-256/byte bindings and fresh codec, color, size, and duration probes |
| `verify_dom.mjs` | Dependency-free real-browser replay and responsive DOM verifier |

All model data, prose, vector art, film frames, and interface graphics were
created for this candidate. The app has no network code, external assets,
personal data, customer data, credentials, or audio.

## Deterministic rebuild

Set `RAPP_FFMPEG`, `RAPP_FFPROBE`, and `RAPP_BROWSER` when the tools are not on
`PATH`. The scripts also check common Windows, macOS, and Linux locations.

From this candidate directory:

```powershell
python .\render.py artifacts
python .\render.py render --ffmpeg $env:RAPP_FFMPEG
python ..\..\scripts\compile_publications.py build .\channel.production.json `
  --ffmpeg $env:RAPP_FFMPEG --ffprobe $env:RAPP_FFPROBE
python .\render.py evidence
python .\render.py delivery --ffprobe $env:RAPP_FFPROBE
python .\render.py check --ffprobe $env:RAPP_FFPROBE
node .\verify_dom.mjs --browser $env:RAPP_BROWSER
```

From the repository root:

```powershell
python -m unittest discover -s tests -p "test_frame_0003_03.py" -v
python scripts\compile_publications.py check `
  candidate-frame-0003\ecosystem-island-threshold\channel.production.json
python scripts\validate_publications.py --ffprobe-local `
  candidate-frame-0003\ecosystem-island-threshold\channel.json
git diff --check
```

The focused test always checks schemas, compiler source transformation,
fixture math, complete series, source and delivery hashes, standalone/privacy
rules, rights, thumbnail, and renderer determinism. When discovered through
`RAPP_BROWSER`, `RAPP_FFMPEG`, and `RAPP_FFPROBE`, it also runs the exact
browser replay, media probes, master decode, and clean candidate-local rebuild.
