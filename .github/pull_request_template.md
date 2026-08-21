<!--
Thanks for contributing to gebra. Fill in the summary, then tick every box that
applies. Leave a box unticked and say why rather than ticking it optimistically —
an unticked box with a reason is a normal review conversation; a wrongly ticked
one is the thing this checklist exists to prevent.
-->

## What this changes

<!-- One or two sentences. Link the issue or task card this closes. -->

## Checklist

### Contributor License Agreement

- [ ] My CLA is on file: I appear in
      [`docs/governance/cla-signatures.md`](../docs/governance/cla-signatures.md),
      or this PR adds my row.
      Not signed yet? See [`CLA.md`](../CLA.md) — signing is manual for now
      and must be done before a first merge.
- [ ] If my employer has rights to this work, section 4 of the CLA is satisfied
      (written permission, or a corporate agreement recorded in the signature
      record).

### Commit and scope

- [ ] Commit messages are [Conventional Commits](https://www.conventionalcommits.org/)
      and carry the task-card ID where the work is card-scoped
      (`feat(ir): canonical JCS emitter [IR-03]`).
- [ ] The task board is updated in the same change as the work it describes
      (contributors with access to the development-process repository).

### Vendored files and goldens

- [ ] The provenance guard passes: `python tools/provenance_guard.py`.
- [ ] No vendored file (`tests/fixtures/properties/**`) is edited in place. If
      this is a sanctioned re-vendor, it follows
      [`docs/governance/re-vendoring.md`](../docs/governance/re-vendoring.md):
      vault-first, `docs/PROVENANCE.md` rows updated, manifest regenerated, all
      in one commit citing the new vault hash.
- [ ] Any golden-file change carries its justification in the commit message.

### Quality gates

- [ ] `ruff check .`, `ruff format --check .`, `mypy` and `pytest` all pass
      locally.
- [ ] Tests accompany the change, and nothing in the test suite executes a
      workflow node, calls an LLM, or opens a network connection.
- [ ] Prose I added (docs, docstrings, CLI output, error messages) claims only
      what the code does — no overstated verification language, and no
      documentation of behaviour that is not merged.
