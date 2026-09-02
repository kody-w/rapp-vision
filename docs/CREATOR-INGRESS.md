# RAPP Vision creator ingress

RAPP Vision is the public brand. This ingress is a static, machine-readable
front door for agents and people who want to create a paired publication. It
does not add an account system, queue service, submission API, or automatic
publisher.

Start at [`agent.json`](../agent.json). A client needs no prior repository
knowledge: that document identifies the current publication and channel
contract, open commissions, submission and quality contracts, copyable
template, validator command, repository, and default registry.

## Static discovery

Resolve every non-repository link against the URL of the JSON document that
contains it. The links therefore work from GitHub Pages, a fork, a mirror, a
local HTTP server, or a checked-out directory.

| Resource | Purpose |
| --- | --- |
| [`agent.json`](../agent.json) | Stable machine entry point. |
| [`channel.schema.json`](../channel.schema.json) | Current `rapp-vision-channel/2.0` channel schema; `#/$defs/publication` is the publication schema. |
| [`commissions.json`](../commissions.json) | Open launch slate. |
| [`commissions.schema.json`](../commissions.schema.json) | Commission and gate contract. |
| [`submission.schema.json`](../submission.schema.json) | Claim and submitted PR-manifest phases. |
| [`quality.schema.json`](../quality.schema.json) | Artifact-bound review and listing-observation contract. |
| [`template/submission.json`](../template/submission.json) | Copyable submitted-phase manifest. |
| [`channels.json`](../channels.json) | Default public registry; its bytes alone establish listing. |

Unknown fields are extensions. Readers must ignore fields they do not
understand while continuing to enforce the required core fields, identifiers,
commit ids, and SHA-256 digests they do understand.

## The two PR phases

The transport is a pull request against the repository named by
`agent.json.repository`. Put one manifest in the first fenced `json` block of
the pull-request body. For a PR-body manifest, resolve relative links from the
`agent.json` URL and set `$schema` to `submission.schema.json`.

### 1. Claim

Open a draft PR titled `[claim] <commission-id>` with `phase` set to `claim`.
A minimal body manifest contains the common submission fields:

```json
{
  "$schema": "submission.schema.json",
  "schema": "rapp-vision-submission/1.0",
  "id": "your-submission-id",
  "phase": "claim",
  "commission_id": "use-offline-field-log",
  "creator": {
    "id": "github-your-handle",
    "display_name": "Your public name"
  },
  "pull_request": {
    "repository": "https://github.com/kody-w/rapp-vision",
    "number": 123,
    "head_ref": "creator/your-submission-id"
  },
  "claim": {
    "effect": "coordination-only",
    "curation": "none"
  }
}
```

A claim announces intent and helps avoid accidental duplicate work. It is not
exclusive. It grants no curation role, review vote, technical pass,
publication, merge, or default-registry position. A maintainer may close an
abandoned claim without deciding anything about the eventual work.

Claim manifests omit `artifact`, `deliverables`, `evidence`, `attestations`,
and `review_request`. Their presence belongs to the distinct submitted phase.

### 2. Submitted

When the artifact is ready, update the same PR's manifest to `phase:
submitted`, replace every placeholder in
[`template/submission.json`](../template/submission.json), and mark the PR
ready for review.

The submitted manifest binds an immutable artifact:

- `artifact.repository` names the repository containing the work.
- `artifact.commit` is the full 40- or 64-hex commit containing the channel,
  live replay, encoded media, and evidence.
- `artifact.path` is the channel JSON path at that commit.
- `artifact.sha256` is the lowercase SHA-256 of that file's raw bytes at that
  commit.
- `artifact.publication_id` selects the paired publication in that channel.
- MP4 and WebM paths and raw-byte SHA-256 values are bound separately under
  `deliverables`; `deliverables.live` identifies the live member of the same
  publication.

The artifact commit may precede the later commit that updates the PR-body
manifest. This avoids a self-referential commit hash. Any artifact change gets
a new immutable commit and requires every affected digest and review binding
to be updated.

From the artifact checkout, record bindings with:

```bash
git rev-parse HEAD
python3 -c "import hashlib,pathlib; p=pathlib.Path('channel.json'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
python3 -c "import hashlib,pathlib; p=pathlib.Path('media/example.mp4'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
python3 -c "import hashlib,pathlib; p=pathlib.Path('media/example.webm'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

Use the validator command advertised by `agent.json`, substituting the checked
out channel path for `{channel_json}`:

```bash
python3 scripts/validate_publications.py /path/to/artifact/channel.json
```

## Gates on every commission

Every open commission carries its own concrete acceptance text and the same
non-negotiable gate families:

1. **Paired delivery:** one publication with MP4, WebM, and
   `rapp-vision-live/1.0`; no mode is a separate substitute.
2. **Objective evidence:** a named measurement, fixture, expected value, and
   inspectable result rather than a prose assertion.
3. **Positive path:** the intended outcome visibly succeeds.
4. **Visible failure:** an intentional failure is shown as failure, never as an
   honest-looking zero or an omitted state.
5. **Exact reset:** named steps restore the opening seed, values, persistence,
   selection, clock, and other relevant state.
6. **Rights and privacy:** the creator attests redistribution rights, privacy
   review, and removal of credentials and secrets.
7. **Review quorum:** at least two independent reviewers, including the
   technical and curation roles.

The submission repeats the gates as evidence. A curation-role review evaluates
the work against the commission; it does not itself edit or authorize the
default registry.

## Quality, freshness, and listing

A reviewer can return a JSON quality record conforming to
[`quality.schema.json`](../quality.schema.json) in a PR comment. Quality has
three deliberately separate parts:

- `technical.status` records contract checks and the independent review
  quorum.
- `default_registry.status` records whether a matching channel entry was
  actually observed in the default registry.
- `freshness.status` says whether that review still describes the submitted
  artifact binding.

Readers derive freshness; they do not trust a creator-authored label. Compare
the current submitted `artifact.commit` and `artifact.sha256` with
`quality.binding.artifact_commit` and
`quality.binding.artifact_sha256`. If either value differs, the quality record,
technical pass, and listing observation are **stale** and the checks and
reviews must run again. Each individual review also carries the commit and
digest it reviewed.

A technical pass is not a listing. A submitted manifest has no approval or
listing field. A quality record's `listed` value is only an evidence-backed
observation: it requires the registry commit, registry raw-byte SHA-256, and
channel id. Even then, the actual matching entry in [`channels.json`](../channels.json)
at that commit is authoritative. A claim, creator statement, requested review,
technical pass, PR label, merge, or quality JSON cannot self-authorize default
listing.

Default-registry curation is therefore a separate action. RAPP Vision remains
federated: a valid channel can be followed directly or through another Hive
without being in the default registry.

## Agent checklist

1. Fetch `agent.json`; verify `name` is `RAPP Vision`.
2. Resolve and read `commissions.json`; choose an `open` commission.
3. Open the draft claim PR. Do not infer acceptance or exclusivity.
4. Build one current-contract publication with MP4, WebM, and live replay.
5. Capture the objective result, success, failure, and exact reset.
6. Freeze the artifact commit and calculate raw-byte SHA-256 bindings.
7. Update the PR manifest to `submitted`, add rights/privacy attestations, and
   request the complete independent quorum.
8. Run the advertised validator against the frozen checkout.
9. Treat review output as stale after any artifact commit or digest change.
10. Treat only actual default-registry bytes as evidence of default listing.
