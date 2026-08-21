# Vendored files: the provenance guard and the re-vendor path

Parts of this repository are **byte-copy snapshots** of the specification vault
`Gebra-Tech/initial-documents`. They are read-only here: the vault copy is
authoritative, and a change made locally would silently fork the contract every
validator, fixture and golden is written against.

This page describes what is guarded, how CI enforces it, and the one sanctioned
way for a vendored file to change.

## What is guarded

| Repository | Guarded surface | Manifest |
|---|---|---|
| `Gebra-Tech/gebra` (this one) | the acceptance fixture corpus, `tests/fixtures/properties/**` | `tools/provenance-manifest.json` |
| the maintainers' development-process repository (private) | the vendored documentation package — SOW, briefs, decision records, research notes, specs | `tools/provenance-manifest.json` there |

Both manifests are derived from the same source of truth: the manifest table in
the development-process repo's `docs/PROVENANCE.md`, which records every
vendored path together with its vault source file and the vault commit it was
copied from. The rows are split across the two repositories only because the
files themselves are.

## How the guard works

`tools/provenance_guard.py` is a dependency-free script that hashes every
guarded file and compares it with the SHA-256 recorded in the manifest:

```bash
python tools/provenance_guard.py                    # what CI runs
python tools/provenance_guard.py --provenance-doc ../<development-process repo>/docs/PROVENANCE.md  # maintainers only
```

It fails, with the offending paths named, on any of:

- **modified** — a guarded file whose bytes differ from the recorded hash;
- **missing** — a manifest entry with no file in the tree;
- **unlisted** — a file inside a guarded tree that no manifest entry covers, so
  a fixture added by hand is caught as surely as one edited by hand;
- **manifest drift** (with `--provenance-doc`) — the manifest and the
  `docs/PROVENANCE.md` rows disagree about which files are vendored or about a
  file's vault source and commit. This is what stops a manifest row from being
  deleted to quietly unguard a file.

A hash manifest was chosen over a git-diff rule deliberately: it holds
regardless of how a change arrived (rebase, squash, force-push, a directory
copied in wholesale), it needs no git history, and only an absolute record can
notice deletions and unlisted additions.

The guard reports byte-equality against a recorded snapshot. It says nothing
about whether the content is correct — that is what the vault's review process
and the fixture review checklist are for.

CI runs the guard as its own job on every push and pull request, in both
repositories.

## The sanctioned re-vendor path

A vendored file changes **vault-first**, never here. There is no bypass flag and
no CI exemption label: the guard passes again only once the manifest records the
new bytes, which is precisely the reviewable event.

1. **Rule it in the vault.** Land the change in
   `Gebra-Tech/initial-documents` with its decision record (`DEC-NN`, or an
   addendum). An IR-affecting change carries an `ir_version` bump. A fixture
   corpus change routes through fixture review sign-off first — a
   validator/fixture mismatch is a logged decision, never a quiet edit.
2. **Copy the bytes.** Replace the local file with the new vault copy verbatim,
   including its vendored-snapshot banner. No local deltas, no reformatting —
   the editor configuration already excludes the corpus from whitespace rules
   for this reason.
3. **Update `docs/PROVENANCE.md`.** Set the vault commit and copied date on
   every re-vendored row.
4. **Regenerate the manifest** in the repository that holds the file:

   ```bash
   python tools/provenance_guard.py --regenerate
   python tools/provenance_guard.py --provenance-doc <path to docs/PROVENANCE.md>
   ```

   `--regenerate` rewrites the hashes from the working tree and carries the
   `vault_source`/`vault_commit` of each existing entry forward; step 3 is what
   updates those, and the cross-check in the second command is what proves the
   two records agree. A file newly added to a guarded tree is written with
   `UNRECORDED` provenance fields — fill them in from its `docs/PROVENANCE.md`
   row before committing, or the cross-check fails.
5. **One commit.** The new bytes, the `docs/PROVENANCE.md` rows and the
   regenerated manifest land together, and the commit message cites the new
   vault commit hash, e.g.:

   ```text
   chore(fixtures): re-vendor mixed/04 from vault a1b2c3d [TE-03]
   ```

   If the changed files span both repositories, that is one commit per
   repository, each citing the same vault hash.
6. **Review.** The reviewer checks the routing evidence — vault decision record,
   fixture review sign-off where applicable, matching hashes — before merge.
   The manifest diff makes the scope of a re-vendor impossible to miss.

## Preparing a corpus proposal

Step 1 needs a proposal to rule on, and a proposal for the fixture corpus is a
set of bytes, not a description. `tools/corpus_reconcile.py` is the worked
example: it holds the one mandated shape-reconciliation pass over the corpus as
data — every edit a *(before, after)* pair of the fixture's literal `expected:`
block, each citing the frozen passage that fixes its target shape. That pass has
since been ruled and re-vendored, so the tool now reads as a record of what
changed and a gate that keeps it changed; the workflow it demonstrates is what a
future corpus proposal follows.

```bash
python tools/corpus_reconcile.py            # what is outstanding, and what it would change
python tools/corpus_reconcile.py --audit    # the full audit report, per item, with citations
python tools/corpus_reconcile.py --check    # exit 1 if any ruled revision were reverted
python tools/corpus_reconcile.py --diff     # the byte-exact patch, as a unified diff
python tools/corpus_reconcile.py --emit out/candidate   # a candidate corpus to lint and attach
python tools/corpus_lint.py --corpus out/candidate      # the candidate must be lint-green
```

Two properties are worth knowing before you rely on it. It refuses to write
inside `tests/fixtures/properties/` — pointing `--emit` at the corpus, or at any
directory containing it, is an error, not a prompt, and that refusal does not
relax once a ruling lands. And it never round-trips YAML: a re-emitted document
would rewrite comments, folded scalars and key order across every file it
touched, which is exactly the drift the byte-copy rule exists to prevent, so
each edit is a literal block substitution that fails loudly if the bytes it
expects are not there.

`--check` is the other half of the same table, and it is what makes "the pass
landed" an observation rather than a claim: it exits 1 while a ruled revision is
missing and 0 once every one is present. Because it reads any corpus given to
it, the test suite reconstructs the pre-ruling bytes in a temporary directory
and requires the tool to reproduce the vendored ones from them — so the claim
that what was merged is exactly what was ruled is checked, not asserted.

## When the guard fails on your branch

Read what it printed:

- Did you edit a vendored file to make something work? Revert it. An
  unimplementable or contradictory passage in a frozen document is a spec
  defect: file it, put the affected task card on hold with the link, and stop at
  the boundary. Never improvise the semantics locally.
- Did you add a file to `tests/fixtures/properties/`? The corpus is a shared
  contract surface; additions route through fixture review, not through your
  branch.
- Are you performing a sanctioned re-vendor? Follow the six steps above; the
  guard turns green when the manifest is regenerated.
- Did an editor or a tool rewrite line endings or trailing whitespace? Restore
  the original bytes; `.editorconfig` already opts the corpus out of every
  whitespace rule.

## A known upcoming change

The VERSION-COMPAT living document (maintained in the development-process
repository) records the supported substrate ranges. Its edit discipline is
"one commit per ceiling change, citing the drift-suite run that justified it";
it is not part of this repository's vendored manifest, and the guard
treats it as one.
