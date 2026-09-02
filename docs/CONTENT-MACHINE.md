# Content machine

The content machine finds gaps in the registered channel network and reviews
published entries against a versioned rubric. It produces reviewable state, not
published episodes:

- `state/proposals.json` is a queue of candidate episodes and follow-ups.
- `state/editorial_reviews.json` is the machine-authored editorial lane.
- `state/metrics.json` is read as viewer-signal input and is never owned or
  rewritten by the content machine.

Both outputs are deterministic JSON snapshots without timestamps. Git history
is their time series.

## Dry-run is the default

`dryrun` is the built-in adapter and the default for every command. It uses no
model, network service, token, or model credits.

For proposals, dry-run fills a deterministic template from the detected gap's
existing evidence. For reviews, it scores only rubric criteria marked
`machine_checkable`; criteria that require editorial judgment remain `null`.
Dry-run records are labelled `judgment: false`, so structural lint cannot be
mistaken for a model's editorial opinion.

```bash
python3 scripts/content_machine.py propose
python3 scripts/content_machine.py review
python3 scripts/content_machine.py run
```

## Model adapters are explicit

An external adapter can be selected with `--adapter module:factory`. An adapter
that declares `needs_model = True` is refused unless the same invocation also
passes `--allow-model` (or sets `RAPP_CONTENT_ALLOW_MODEL=1`).

```bash
python3 scripts/content_machine.py run \
  --adapter your_package.your_module:make_adapter \
  --allow-model
```

The repository does not ship a model adapter. `--allow-model` is only a consent
gate; it does not provide a model, credentials, provider, or implementation.
Without a valid explicit adapter, the script falls back to dry-run.

## Candidate-only output

A proposal is a candidate, not a publication. The machine may preserve human
status, notes, and edits in the queue, but it never adds an entry to a
`channel.json`, changes media, or updates the player. Editorial reviews stay in
their own machine lane and are never summed into viewer reactions or other
human counters.

This boundary is enforced twice:

1. `write_json()` rejects every destination outside the selected `state/`
   directory, and review snapshots always pass through that guard.
2. The scheduled workflow rejects any changed path other than
   `state/proposals.json` and `state/editorial_reviews.json`.

The automation branch is pushed to `automation/content-machine` and offered as
a pull request. It does not push to protected `main`.

## Promotion boundary

Promotion is a separate, explicit act. A person—or a separately designed and
authorized promotion process—must choose a proposal, create the actual episode
and media, edit the target `channel.json`, and submit that publication through
the repository's normal review path.

Do not broaden the content-machine workflow's allowlist to make promotion
convenient. Candidate generation and publication have different authority,
failure modes, and review requirements; keeping them separate is the publish
guard.
