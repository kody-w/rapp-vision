# Working Proofs

**Useful work, measurable results, controls included.**

Working Proofs is a recurring public channel for reviewed RAPP Vision work. Its
first release promotes six cycle-2 through cycle-4 publications in this order:

1. **Why the Grid Overflows**
2. **Triage Invoices Without a Pointer**
3. **Six Shapes, One Grid**
4. **Will the Island Herd Hold?**
5. **Read the Wetland Twice**
6. **Fogline Survey**

The aggregate does not copy apps, thumbnails, masters, or encoded media.
Instead, `channel.json` resolves each publication asset from its reviewed source
under `candidate-frame-0002/`, `candidate-frame-0003/`, or
`candidate-frame-0004/`.
`evidence-index.json` binds every source `channel.json`, `evidence.json`, and
`delivery.json` by the SHA-256 of its raw bytes.

Rebuild and verify the aggregate with:

```bash
python3 scripts/build_working_proofs.py
python3 scripts/build_working_proofs.py --check
python3 scripts/validate_publications.py --ffprobe-local working-proofs/channel.json
python3 -m unittest tests.test_working_proofs -v
```

The source candidates remain the authority for their behavior, evidence, and
media. The builder only deep-copies the selected publication metadata, removes
review-only fields, and rebases relative URLs for this channel.

`screenshots/` contains real Edge captures of every configured checkpoint after
the exact aggregate live actions run at the 960 px desktop player stage and the
390 px iframe stage. Fogline adds challenge, rejected-wall, trap, optimal
success, exact-reset, and untouched FOG-7 handoff captures, followed by a real
player takeover check. Every result capture includes the player lower third,
and `manifest.json` records screenshot hashes plus the measured visible
intersection for each configured result selector. The manifest also binds the
player, aggregate channel and evidence index, and every source app, channel,
and evidence document. Freshness compares checkpoint state and geometry while
the committed PNG hashes authenticate only the captures made by the recorded
browser.
