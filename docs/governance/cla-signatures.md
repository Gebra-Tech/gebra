# CLA signature record

The authoritative list of contributors whose Contributor License Agreement is on
file. A pull request may not be merged unless its author has a row here (WA-08).

- The agreement is [CLA.md](../../CLA.md); the signing procedure is its
  "How to sign" section.
- The process is **manual** until the CLA bot lands. Only the
  maintainer edits this file, and only after archiving the signed statement. A
  CLA bot that checks pull requests automatically is deferred to the 1.0 launch —
  when it lands, this table is the data it reads.
- Rows are append-only. A contributor who signs a later CLA version gets an
  additional row; existing rows are never rewritten, so it stays visible which
  version covered which period.

## Columns

| Column | Meaning |
|---|---|
| `GitHub handle` | The account whose commits and pull requests the row covers. |
| `Legal name` | The name on the signed statement. |
| `Type` | `ICLA` (individual) or `CCLA` (corporate, entity named in `Notes`). |
| `CLA version` | Version of `CLA.md` that was signed. |
| `Signed` | Date on the contributor's statement (YYYY-MM-DD). |
| `Recorded` | Date the maintainer added the row (YYYY-MM-DD). |
| `Archive` | Where the signed statement is filed, e.g. `email 2026-07-30`. |
| `Notes` | Employer/entity, scope limits, or a superseding row. |

## Signatures

| GitHub handle | Legal name | Type | CLA version | Signed | Recorded | Archive | Notes |
|---|---|---|---|---|---|---|---|
| _(none recorded yet)_ | | | | | | | |

The repository owner's own commits are not contributions under the agreement —
Gebra Tech, Inc. holds that work directly — so no row is required for them.

## Verifying at review time

The pull-request template points here. The check is a
literal one: find the pull-request author's handle in the table above, confirm
the `Type`/`Notes` cover the contribution (an employer-owned contribution needs
a `CCLA` row), and only then approve. No row, no merge — the correct response is
to point the contributor at [CLA.md](../../CLA.md), not to merge and follow up.
