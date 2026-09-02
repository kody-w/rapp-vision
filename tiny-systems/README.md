# Tiny Systems

Three original deterministic micro-lessons seed RAPP Vision with distinct
landscape, square, and portrait publications. Every entry ships one guided
film and one live replay covering an accepted path, a visible rejected path
that preserves accepted state, and an exact reset.

The complete delivery is reproducible from repository-owned sources:

```bash
python3 scripts/render_tiny_systems.py
python3 scripts/compile_publications.py build tiny-systems/channel.production.json
python3 scripts/validate_publications.py --ffprobe-local tiny-systems/channel.json
```

`channel.production.json` is the authoring source, `masters/` contains the
lossless deterministic renders, and `delivery.json` binds every master and
encoded file by SHA-256. The interactive claim states and selectors are
recorded separately in `evidence.json`.
