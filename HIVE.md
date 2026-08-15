# RAPP Hive static federation

RAPP Hive is a many-to-many federation layer. A Hive is a static JSON object,
not a server or account. Hives can be public or private, and one AI can attach
to several Hive objects at the same time.

Attaching is not publishing. A private Hive remains private until its owner
explicitly gives it a reachable URL.

## `rapp-hive/1.0`

The machine-readable contract is [`hive.schema.json`](hive.schema.json).

```json
{
  "schema": "rapp-hive/1.0",
  "id": "example.public.media",
  "name": "Example Public Hive",
  "visibility": "public",
  "revision": {
    "sequence": 7,
    "updated": "2026-08-15T23:00:00Z"
  },
  "channels": [
    {
      "id": "example-channel",
      "name": "Example Channel",
      "url": "https://example.net/channel.json",
      "repo": "https://github.com/example/channel"
    }
  ],
  "peers": [
    {
      "id": "research-hive",
      "url": "https://example.org/hive.json",
      "mode": "pull"
    }
  ]
}
```

| Field | Rule |
| --- | --- |
| `schema` | Must be `rapp-hive/1.0`. |
| `id` | Stable identity for this Hive across mirrors and revisions. |
| `visibility` | `public` or `private`. Descriptive policy, never an authorization mechanism. |
| `revision.sequence` | Monotonically increasing integer for comparing two snapshots with the same Hive `id`. |
| `revision.updated` | ISO-8601 evidence for humans; sequence remains authoritative. |
| `channels` | Static channel references. Existing RAPP Vision `channels` entries remain compatible. |
| `peers` | Optional static Hive references to pull during synchronization. |

Unknown fields must be ignored so a v1 reader can consume an extended object.

## Public and private Hives

- A **public Hive** is reachable by URL and may list other public Hives as peers.
- A **private Hive** uses the same schema but may live in a private repo, on a
  LAN, or only on one device.
- `visibility: "private"` does not encrypt an object. Access control belongs to
  its storage/transport boundary.
- A client must never upload, announce, or add a private Hive to a public peer
  merely because the client attached to both.
- A private Hive may pull from a public Hive without becoming public.

## One AI, multiple Hives

Attachment is client-owned configuration:

```json
{
  "ai": "local-agent:researcher",
  "hives": [
    { "id": "rapp.public.vision", "url": "https://kody-w.github.io/rapp-vision/channels.json" },
    { "id": "team.private.media", "url": "https://media.lan/hive.json" },
    { "id": "personal.notes", "object": "local://hives/personal-notes.json" }
  ]
}
```

The AI reads a merged view while each source object keeps its identity,
visibility, revision, and owner. Multiple AIs can attach to the same Hive, and
one AI can attach to multiple Hives.

## Deterministic synchronization

1. Read explicitly attached root Hives in the client's stored priority order.
2. Traverse each root's `peers` sorted by `(id, url)`.
3. Canonicalize URLs and keep a visited set. A visited Hive is not traversed
   twice, so peer cycles terminate.
4. If snapshots share a Hive `id`, keep the greatest
   `revision.sequence`; ties use the lexicographically smaller canonical source
   URL. Refuse a negative or non-integer sequence.
5. Merge channel entries by stable channel `id`. The first selected Hive in
   root-priority/traversal order wins. Record shadowed sources for diagnostics;
   never silently combine two channel bodies.
6. A failed or unauthorized Hive is `unavailable`, not an empty successful Hive.
   Other attached Hives continue to contribute.

This is synchronization by repeatable static merge. It is not distributed
mutation, consensus, or automatic write-back.

## RAPP Vision compatibility

`channels.json` is the default public Hive and keeps its existing
`channels` array, so current RAPP Vision readers continue to work. The
`visibility`, `revision`, and `peers` fields are additive metadata.

Copy [`template/hive.json`](template/hive.json) to start another static Hive.
