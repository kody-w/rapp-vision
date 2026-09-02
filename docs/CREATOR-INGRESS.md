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
| [`channel.production.schema.json`](../channel.production.schema.json) | One-master authoring contract that retains the mandatory live replay. |
| [`template/channel.production.json`](../template/channel.production.json) | Copyable source for deterministic paired-media compilation. |
| [`scripts/compile_publications.py`](../scripts/compile_publications.py) | Checks, plans, and builds both required codecs before publishing `channel.json`. |
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
    "display_name": "Your public name",
    "github_user_id": 12345678
  },
  "pull_request": {
    "repository": "https://github.com/kody-w/rapp-vision",
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

The pull request number is omitted when opening the claim because GitHub has
not assigned it yet. It may be added afterward. A workflow validating an
existing PR passes its transport-derived number to the semantic validator;
creator-written PR metadata is never treated as authority.
The same workflow requires `creator.id` and `creator.github_user_id` to match
the authenticated pull-request author; spelling a different identity into the
manifest cannot make the author an independent reviewer.

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

Review requests name required roles, not guessed identities. The protected
review workflow assigns authenticated reviewers after submission. Technical
and curation reviewers must be distinct, neither may be the creator, and every
review is bound to the complete submitted manifest.

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

Then run the semantic submission validator advertised by
`agent.json.submission_validator`:

```bash
python3 scripts/validate_creator_submission.py submission submission.json \
  --artifact-root /path/to/frozen/artifact/checkout
```

The artifact root must be a clean Git checkout whose `HEAD` and
`remote.origin.url` match the submitted commit and repository. The protected
PR workflow also supplies `--pr-number` from the event rather than trusting
creator-authored metadata. The validator recomputes the channel, MP4, and WebM
hashes; verifies that all three
deliverables name the selected publication; validates the live replay; checks
every repository-owned live application and objective evidence path exists;
probes H.264 and VP9 rather than trusting file extensions; rejects duplicate
codec sources and URL-ambiguous encoded paths; rejects template sentinels; and
prints the canonical submitted-manifest digest used by every later review.

An agent beginning with one local guided-film master can use the production
contract advertised by `agent.json.production`:

```bash
python3 scripts/compile_publications.py check channel.production.json
python3 scripts/compile_publications.py build channel.production.json
```

The build has no single-codec or replay-skipping mode. It probes H.264 for MP4
and VP9 for WebM, installs neither file unless both pass, and writes the final
v2 channel last. The production schema is therefore an authoring convenience;
the submitted artifact remains the constitutional v2 channel.

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

Individual reviewers return evidence through authenticated GitHub review
events. Only the protected workflow named by a quality record's `authority`
may aggregate those events into authoritative JSON conforming to
[`quality.schema.json`](../quality.schema.json). A JSON block pasted by an
ordinary PR commenter is an untrusted proposal, not a quality decision.
Quality has three deliberately separate parts:

An approving review declares exactly one role and the current canonical
submission digest in its body:

```html
<!-- rapp-vision-review role=technical submission_sha256=<64 lowercase hex> -->
```

The other required role uses `role=curation`. The workflow follows every review page and ignores comments,
stale digests, non-approving review states, malformed markers, and superseded
reviews. It takes reviewer identity from GitHub's authenticated review event,
including the stable numeric GitHub user id, never from the manifest or marker
text.

- `technical.status` records contract checks and the independent review
  quorum.
- `default_registry.status` records whether a matching channel entry was
  actually observed in the default registry.
- `freshness.status` says whether that review still describes the submitted
  artifact binding.

Readers derive freshness; they do not trust a creator-authored label. The
quality binding includes a canonical submitted-manifest digest covering the
commission, creator, artifact tuple, both media paths and hashes, live member,
evidence, attestations, and requested quorum. It also repeats
`artifact.commit` and `artifact.sha256`. If any binding differs, the quality
record, technical pass, and listing observation are **stale** and the checks
and reviews must run again. Each individual review carries the same submission
digest, commit, and artifact digest.

Before accepting a quality record, run:

```bash
python3 scripts/validate_creator_submission.py quality \
  submission.json quality.json \
  --repository "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY" \
  --run-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" \
  --pull-request-number "$PR_NUMBER" \
  --pull-request-head-sha "$PR_HEAD_SHA" \
  --review-state-sha256 "$REVIEW_STATE_SHA256"
```

The validator derives quorum rather than trusting `quorum.met`: every check
must pass, passing reviewer identities must be distinct and non-creator,
technical and curation roles must both be present, and every review binding
must match the submitted manifest.

Approval is revocable. Every quality artifact binds the PR number, current
head SHA, and a digest of the complete latest authenticated review state.
Submitted, edited, and dismissed review events all rerun the stable
`Creator Submission Review / review` check. A pending or revoked quorum makes
that latest check fail. Downloadable artifacts from older runs are historical
records and are not authoritative; a consumer must require the latest check
for the current PR head and current review-state digest.

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
4. Build one current-contract publication with MP4, WebM, and live replay;
   use the advertised production compiler when starting from one master.
5. Capture the objective result, success, failure, and exact reset.
6. Freeze the artifact commit and calculate raw-byte SHA-256 bindings.
7. Update the PR manifest to `submitted`, add explicit rights/privacy
   attestations, and request the technical and curation roles.
8. Run both advertised validators against the frozen checkout.
9. Treat review output as stale after any artifact commit or digest change.
10. Treat only actual default-registry bytes as evidence of default listing.
