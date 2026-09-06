# Inside Immunity

**T Cells: Recognize, Respond, Remember** is an original five-minute illustrated
lesson with narration and synchronized captions.

- Guided film: `media/t-cells.mp4` and `media/t-cells.webm`.
- Live companion: `apps/t-cell-lab.html`, driven by the script in `channel.json`.
- Scientific references: `sources.html` and `sources.json`.
- English subtitles: `captions/t-cells.en.srt` and `captions/t-cells.en.vtt`.

The MP4 preserves the completed master without another lossy encode. The WebM
is a VP9/Opus companion of the same film. Both are 1920x1080 at 30 fps.

## What the live model proves

The lab follows one simplified CD8 clone. An activated effector with its
matching peptide-MHC I target can commit a controlled-cell-death signal.
Different peptides, MHC II, an unactivated effector, and antibody manufacture
are explicitly rejected. A rejected operation preserves the accepted result;
selecting a scenario starts a new proposed encounter while retaining the
previous accepted receipt.

Reset restores the opening scenario, target, counters, receipt, and status.
Allow the short visual transition to settle. There is no persistence,
unseeded randomness, or hidden clock to reset. The counters are software trial
counts, not biological measurements.

This is a teaching schematic, not a complete immune simulation, clinical
prediction, or personal medical advice. The film and sources explain the
important limits of thymic tolerance, memory, vaccination, and immunotherapy.

## Recheck

```sh
python3 scripts/validate_publications.py --ffprobe-local inside-immunity/channel.json
python3 -m unittest discover -s tests -p test_inside_immunity.py -v
```

The publication contains only the reviewed film and public-facing companion
assets. Private production notes, chats, workstation paths, and credentials
are not part of this channel.
