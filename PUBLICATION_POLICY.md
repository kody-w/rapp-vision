# RAPP Vision Publication Constitution

Every new RAPP Vision publication is one work with two inseparable modes:

1. **Guided video:** encoded MP4 and WebM media. This is the default watch mode
   and the newcomer orientation layer.
2. **Live replay:** a valid `rapp-vision-live/1.0` interaction script. This is the
   take-the-wheel proof, available from the same watch permalink.

A publication missing either mode is invalid. MP4-only, WebM-only, static-only,
and replay-only submissions are rejected.

The modes share identity, not necessarily runtime. Entry `duration` and
`chapters` describe the default encoded film. Replay length is derived from its
scenes unless `live.duration` states it explicitly; `live.chapters` is optional
and belongs only to the replay.

The current contract is `rapp-vision-channel/2.0`, documented by
[`channel.schema.json`](channel.schema.json) and enforced by
[`scripts/validate_publications.py`](scripts/validate_publications.py). The
validator, not descriptive prose, decides whether a publication is admissible.

[`channel.production.schema.json`](channel.production.schema.json) is an
authoring contract, not a second publication format. Its compiler accepts one
local master plus the required live replay, emits both encoded media formats,
and produces the same `rapp-vision-channel/2.0` object enforced above.

## Frozen legacy exception

Material published before this constitution remains playable only when all
three values match the frozen
[`policy/legacy-publications.json`](policy/legacy-publications.json):

- channel id;
- canonical channel URL; and
- publication id; and
- SHA-256 of the complete normalized publication object.

The exception is an allowlist of existing identities, not permission to publish
new v1 material. Adding a URL to `channels.json`, copying the legacy marker, or
adding a new publication to an allowlisted channel does not confer legacy
status. A dedicated `pull_request_target` gate checks out the trusted base and
runs only its minimal freeze verifier against the candidate git object; it
never executes the PR's validator. Protected-branch pushes source that verifier
from `github.event.before`, so multi-commit pushes cannot choose their own
baseline. The browser and CLI reject an allowlisted id whose content no longer
matches its digest. Once migrated to v2, a publication follows the paired
contract.

### Two-stage trust-root bootstrap

The initial installation is intentionally split:

1. Push a manually reviewed commit containing only
   `.github/workflows/legacy-freeze.yml` and
   `scripts/trusted_legacy_freeze.py`. `--bootstrap-check` rejects a policy in
   this commit.
2. Push the policy implementation. The trusted stage-one verifier permits
   `policy/legacy-publications.json` only when its raw SHA-256 is exactly
   `1ec1cf780bf6f31c593da19d7ff4008313b5ed39add09137ec1c539169cd8a50`.
3. From then on, the verifier requires byte identity for the workflow, verifier,
   and policy. Modification or deletion of any trust-root file is rejected.

## Rationale

Encoded media makes the work dependable and approachable. The live replay makes
the proof inspectable, interruptible, and remixable. Either format alone breaks
the promise: orientation without agency is ordinary video; agency without
orientation asks newcomers to begin inside an unexplained machine.
