# Scheduled automation under protected `main`

Scheduled publishers never push to `main`. Each run fetches current `main`,
rebuilds a stable automation branch from that commit, publishes with
`--force-with-lease` only to that automation branch, and creates or updates a
review-ready pull request.

| Workflow | Branch |
|---|---|
| Follow index | `automation/harvest-follows` |
| Metrics snapshot | `automation/metrics` |
| Content machine state | `automation/content-machine` |

The workflows request `contents: write` and `pull-requests: write`; none receives
a ruleset bypass. Runs are serialized per publisher so two schedules cannot
race the same branch.

GitHub deliberately does not trigger a new workflow run from many events
created by the repository `GITHUB_TOKEN`. These pull requests therefore remain
review-ready for a person or separately authorized merge queue to inspect,
refresh checks, and merge. Do not work around that behavior with a bypass,
personal token, direct push, automatic merge, or force push to `main`.
