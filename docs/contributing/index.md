# Contributor guide

From a clone to a first change that merges. This page is the path: what to sign, how work is
chosen, which files you may not edit, what a commit message has to carry, and what happens to
your pull request after you open it.

It is deliberately a companion to [CONTRIBUTING.md](https://github.com/Gebra-Tech/gebra/blob/main/CONTRIBUTING.md)
rather than a replacement for it. That file is the mechanics reference — the exact setup
commands, the four quality gates, the compatibility matrix, the drift suite and the release
procedure — and it stays authoritative on all of them. This page is the order you do things in
and the reasoning behind the rules that are not style preferences, and it links into
CONTRIBUTING.md at each step rather than restating it.

Nine numbered sections, in the order a first contribution meets them, and then a walkthrough over
one real card. Most of the sections describe a rule that will refuse your change if you skip it,
so they are worth reading before you write code rather than after CI says no.

## 0. Where everything lives

Two repositories, and knowing which is which explains most of what follows.

| Repository | Holds | Who reads it |
|---|---|---|
| `Gebra-Tech/gebra` — this one | the library, its tests, its tooling, and the documentation site you are reading | everyone |
| the maintainers' development-process repository (private) | the statement of work, the frozen specifications, the decision records, the task boards and the plan | maintainers |

A third repository sits behind both: the specification **vault**, where a frozen document changes
first. You will never interact with it directly, and it is still the reason for several of the
rules below — because parts of the other two repositories are **copies** taken from it. Part of
what this repository holds is one: the acceptance fixture corpus under
`tests/fixtures/properties/`. Most of what the private repository holds is too — the statement of
work, the briefs, the frozen specifications, the decision records and the research notes. Those
copies are byte-for-byte snapshots, and a guard in CI checks that they still are.

That arrangement is what sections 4, 5 and 6 are about, and it is why "edit the specification so
that the code is right" is never an available move.

Nothing in this arrangement is a barrier to contributing. It means the answers to "why does the
build refuse this?" are written down somewhere, and this page tells you where.

## 1. Sign the CLA

Every contribution needs a signed **Contributor License Agreement** with Gebra Tech, Inc. before
it can be merged. This is not a formality that gets sorted out at merge time: a pull request
whose author has no row in the signature record is not merged, and the correct response to one
is a pointer back here rather than a merge with a follow-up.

The agreement is [`CLA.md`](https://github.com/Gebra-Tech/gebra/blob/main/CLA.md), and its
"How to sign" section is the procedure. In short: email `gebra.dev@gmail.com` with the signing
statement that section prints, from the address you want on file, before you open your first
pull request. The maintainer archives the email and adds your row to
`docs/governance/cla-signatures.md`. That table — not your email, not the pull-request
description — is what a reviewer checks.

Two details that catch people:

- **The process is manual today.** No bot comments on your pull request to tell you the CLA is
  missing; a reviewer looks the row up by hand. `CLA.md` records that an automatic check is
  deferred to the 1.0 launch, and that when it lands it reads the same table.
- **If your employer has rights to what you write, section 4 of the CLA applies.** Either get
  written permission or have your employer execute a corporate agreement — email the same
  address and the maintainer handles it, then records it as a `CCLA` row. Doing this after the
  fact is much harder than doing it first.

Rows are append-only. Signing a later version of the agreement adds a row; it never rewrites
the one you already have, so which version covered which period stays visible.

## 2. Set up, and run what CI runs

CONTRIBUTING.md has the full setup, including the pip path and the compatibility matrix. The
short version:

```bash
git clone https://github.com/Gebra-Tech/gebra.git
cd gebra
uv sync --extra dev     # creates .venv exactly as uv.lock pins it
```

Four gates decide whether a change is well-formed, and each reads its configuration from
`pyproject.toml`, so running them locally checks the same thing the CI job checks:

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (drop --check to apply)
uv run mypy                    # strict type check over src/, tests/ and tools/
uv run pytest                  # the test suite
```

Those four are the ones you will run constantly. They are not, however, everything: CI runs
**eighteen jobs**, and several of them are guards that no amount of local `pytest` will
anticipate because they judge the *shape* of your change rather than its behaviour — the
provenance guard (section 4), the honest-claims lint (section 8), the golden-file guard, the
corpus lint, and the documentation build. Section 8 lists what each one refuses.

Two conventions worth adopting immediately, because reviewers will otherwise ask for them:

- **Tests accompany the change**, because the claims this project makes about a workflow have to
  be claims a test demonstrates. There is a coverage floor as well, on three scopes, and
  `docs/governance/coverage-gate.md` is where it and its exemption policy are written down.
- **Nothing in the test suite may execute a workflow node, call an LLM, or open a network
  connection.** This is the project's central invariant, not a testing preference: gebra reads
  definitions and never runs them, and the suite is where that stays true. The sample workflows
  in `tests/sample_workflows/` are built so that any node body that *is* called records the call
  and raises, and the documentation examples run under a guard that refuses sockets, name
  resolution and the whole `invoke` family. If you add a path that reads a new kind of workflow
  object, the tripwire for it lands in the same change.

## 3. Find a card: the boards and the dependency gate

Work in this project is **card-scoped**. A card is a unit of work on a task board with an
objective, an acceptance checklist, and a list of prerequisites; the boards live in the private
development-process repository, one per track, and work that is not a card does not merge —
trivial chores of half an hour or less excepted.

You do not need access to the boards to contribute — see the end of this section — but you do
need to understand the rule they enforce, because it is the reason a maintainer will sometimes
say "not yet" to a perfectly good change.

### The rule

A card is **READY**, and therefore claimable, when three things hold at once:

1. its own status is `todo`;
2. every prerequisite **card** it names has status `done`;
3. every prerequisite **gate** it names has been signed.

A `todo` card that fails either of the last two is **BLOCKED** — the word is exact, and the
refusal names what is unmet. A card in any other status (`in-progress`, `in-review`, `on-hold`,
`done`, `dropped`, `superseded`) is neither: it is not a candidate at all. `done` in particular
is terminal, so a defect found in finished work becomes a *new* card rather than a reopened one.

READY is never stored anywhere. It is computed from the boards each time it is asked for, which
is why a card can become claimable without anyone editing it: the moment its last prerequisite
flips to `done`, it is READY.

The maintainers' tooling applies exactly this rule. `/next-task` reads every board, computes the
READY set, ranks it, and — asked about a specific card that is not READY — refuses and names the
blocking tokens with their current statuses rather than softening the answer. The arithmetic it
performs is small enough to show:

<!-- gebra:example id=the-dependency-gate -->
```python
import re
from pathlib import Path

# A miniature board, in the format the real ones use. Written to disk and read back,
# so what follows parses a file rather than a Python literal.
Path("demo-board.md").write_text(
    """
### DEMO-01 — The models
- **status:** done
- **prereqs:** none

### DEMO-02 — The engine over the models
- **status:** todo
- **prereqs:** DEMO-01

### DEMO-03 — The report the engine feeds
- **status:** todo
- **prereqs:** DEMO-02, GB

### DEMO-04 — The polish pass
- **status:** todo
- **prereqs:** DEMO-01, GA
""",
    encoding="utf-8",
)

# Gate sign-off is recorded in the plan's gate table, not on the cards. These two
# gates are invented for the sketch, like the four cards above.
GATES = {"GA": "signed", "GB": "open"}

cards: dict[str, dict[str, str]] = {}
current = ""
for line in Path("demo-board.md").read_text(encoding="utf-8").splitlines():
    heading = re.match(r"### ([A-Z]+-[A-Z0-9]+) — ", line)
    if heading is not None:
        current = heading.group(1)
        cards[current] = {}
    field = re.match(r"- \*\*(status|prereqs):\*\* (.+)", line)
    if field is not None and current:
        cards[current][field.group(1)] = field.group(2)


def unmet(card: dict[str, str]) -> list[str]:
    """Every prerequisite token that is not satisfied yet, with why."""
    if card["prereqs"] == "none":
        return []
    blocking = []
    for token in (token.strip() for token in card["prereqs"].split(",")):
        if token in GATES:
            if GATES[token] == "open":
                blocking.append(f"{token} (open)")
        elif cards[token]["status"] != "done":
            blocking.append(f"{token} ({cards[token]['status']})")
    return blocking


for name, card in cards.items():
    if card["status"] != "todo":
        print(f"{name}: not a candidate — {card['status']}")
    elif unmet(card):
        print(f"{name}: BLOCKED — {', '.join(unmet(card))}")
    else:
        print(f"{name}: READY")
```

<!-- gebra:output id=the-dependency-gate -->
```text
DEMO-01: not a candidate — done
DEMO-02: READY
DEMO-03: BLOCKED — DEMO-02 (todo), GB (open)
DEMO-04: READY
```

That is the whole gate. `DEMO-02` is claimable because its one prerequisite is finished;
`DEMO-04` is claimable because its gate is signed as well; `DEMO-03` is not, and the refusal
names both reasons rather than one. The code above is the rule, written out so you can see it —
it is not a gebra API, and the real tooling reads real boards rather than a four-card sketch.

### Claiming, and the two things that follow

Claiming a card is a commit, not an announcement: the card's `status` becomes `in-progress` and
`claimed_by` records who and when, in a `chore(plan): claim <ID>` commit. First merged wins.
Releasing a card back to `todo` is always allowed and is preferred over holding one you are not
working on.

Two rules ride along with the gate, and both exist because someone once wanted an exception:

- **If a dependency edge looks wrong, change the edge — do not step over it.** That is a change
  to the board, reviewed like any other, and it is a different conversation from "let me start
  early". Exploration that merges nothing is exempt, because nothing merges.
- **A status change lands with the work it describes**, so the board and the tree never disagree
  about what is finished.

The boards are held to their own rules mechanically. `tools/board_integrity.py` — in this
repository, stdlib-only like the provenance guard — reads every board and the plan's gate table
and refuses a duplicate card identifier, a prerequisite that names no card or gate, a dependency
cycle, a status outside the seven, a `done` card with an unchecked box or no artifacts, a card
sitting in the wrong section, and, given an earlier board state, a status change that is not an
arrow of the transition diagram; a claim with no linked activity for more than five working days
is flagged as stale rather than failed. The maintainers' `/plan-status check` runs that script,
and the development-process repository's CI runs it on every push, so a skill verdict and a CI
verdict cannot differ. It finds the boards on its own where the development-process repository
is checked out beside this one:

```bash
python tools/board_integrity.py
```

### If you do not have board access

Most contributors will not, during the private phase. The route is an issue on this repository:
describe what you want to change, and the maintainer either points you at the card that covers
it or files one. The dependency gate still applies to your change — it is a fact about the
build's ordering, not about permissions — so an answer of "this waits on X" is the gate talking
and not a judgement about the contribution.

## 4. What you may not edit: vendored files

This repository's share of the **byte-copy snapshots** described in section 0 is one tree: the
acceptance fixture corpus, `tests/fixtures/properties/`. It is read-only here, and the reason is
not ceremony — a local edit forks the contract that every validator, fixture and golden file is
written against, silently and in one direction.

`tools/provenance_guard.py` enforces it. It hashes every guarded file, compares each hash with
the one recorded in `tools/provenance-manifest.json`, and fails on four distinct things: a
**modified** file whose bytes differ, a **missing** one the manifest still lists, an
**unlisted** one that appeared inside a guarded tree, and — only when it is handed the
provenance table to compare against, which is `--provenance-doc` and which the development-process
repository's CI passes — a **manifest drift** where the two records disagree. The bare command
below runs the first three. There is no bypass flag and no exemption label.

Nothing is unguarded by that split: deleting a manifest row to quietly unguard a fixture leaves
the file itself inside a guarded tree, where the **unlisted** check finds it. What the
cross-check adds is agreement about *provenance* — which vault file and which vault commit a row
claims — and that is checked where both records live.

Run it yourself — it needs no dependencies and no install:

```bash
python tools/provenance_guard.py
```

Three of the four failures, on a sandbox tree built for the purpose:

<!-- gebra:example id=the-provenance-guard -->
```python
from pathlib import Path

from tools.provenance_guard import Manifest, format_report, regenerate, verify

# A guarded tree of two files, standing in for the fixture corpus.
root = Path("sandbox")
(root / "vendored").mkdir(parents=True)
(root / "vendored" / "spec.md").write_text("frozen bytes\n", encoding="utf-8")
(root / "vendored" / "fixture.yaml").write_text("id: positive-01\n", encoding="utf-8")

seed = Manifest(
    schema_version=1,
    vault_repo="Example-Org/sandbox-vault",  # invented, like the tree — not the real vault
    snapshot_commit="0000000",
    guarded_trees=("vendored",),
    guarded_files=(),
    entries=(),
)
manifest = regenerate(seed, root, Path("manifest.json"))
print(format_report(verify(manifest, root), manifest, root))

# Now the three ways a branch breaks it: an in-place edit, a deletion, and a file
# added to a guarded tree by hand.
(root / "vendored" / "spec.md").write_text("edited to make a test pass\n", encoding="utf-8")
(root / "vendored" / "fixture.yaml").unlink()
(root / "vendored" / "extra.yaml").write_text("id: added-by-hand\n", encoding="utf-8")

print()
for line in format_report(verify(manifest, root), manifest, root).splitlines()[:4]:
    print(line)
```

<!-- gebra:output id=the-provenance-guard -->
```text
provenance guard: OK — 2 vendored file(s) byte-identical to the manifest (vault Example-Org/sandbox-vault@0000000)

provenance guard: FAILED under sandbox
  modified: vendored/spec.md — bytes differ from the recorded snapshot
  missing:  vendored/fixture.yaml — listed in the manifest, absent from the tree
  unlisted: vendored/extra.yaml — inside a guarded tree, absent from the manifest
```

The example prints the first four lines and stops; the real report goes on to say what to do
about the failure, which is the subject of the next two sections. Note the last line shown
especially: a file **added** to a guarded tree is caught exactly as firmly as one edited, because
the manifest is an absolute record rather than a diff rule. That
is deliberate — only an absolute record notices a deletion or an addition at all, and it holds
however the change arrived, including through a rebase, a squash or a directory copied in
wholesale.

A hash match is byte-equality against a recorded snapshot and nothing more. It says nothing
about whether the content is right; that is what the vault's own review process is for.

**The sanctioned way for a vendored file to change** is vault-first: the change is ruled in the
vault with its decision record, the new bytes are copied here verbatim, the provenance table is
updated, the manifest is regenerated, and all of that lands in **one** commit citing the new
vault hash. The guard turns green again at exactly the moment the manifest records the new
bytes, which is precisely the event a reviewer should be looking at. The six steps are in
[re-vendoring.md](https://github.com/Gebra-Tech/gebra/blob/main/docs/governance/re-vendoring.md),
along with what to do when the guard fails on your branch.

## 5. When a frozen document cannot be implemented

Sooner or later you will hit a passage in a specification that cannot be implemented as written
— it contradicts another passage, or it names a shape nothing can produce, or two readings of it
lead to different code and the text does not choose. This is common enough to have a name and a
procedure.

**It is a spec defect, and the procedure is: stop at the boundary.**

1. **File the defect.** Write down the passage, both readings if there are two, what each one
   would cost, and what the code currently does. A defect write-up that names only the problem
   makes the ruling harder than one that names the options.
2. **Put the card on hold** with a link to the defect. `on-hold` is a real status and it carries
   a `hold_reason`; a card sitting quietly `in-progress` while its author waits for an answer is
   the failure mode this exists to prevent.
3. **Do not improvise the semantics.** Not locally, not "just for now", not behind a flag. A
   local reading that turns out to disagree with the ruling is worse than no implementation,
   because it ships and gets depended on.
4. **The ruling lands in the vault**, with a decision record — and, when it changes the
   intermediate representation, an `ir_version` bump — and is then copied back here in one
   commit citing the new vault hash. The held card returns to `todo` once that ruling is
   re-vendored and every card it affects has been re-planned; it is then claimed again like any
   other, rather than resumed where it stopped.

The thing to internalise is step 3, and the reason it holds is not discipline. The one shortcut a
stuck implementer reaches for — change the frozen document so the code is right — is what the
guard in section 4 makes unavailable, including by accident; and improvising *without* touching
the document leaves nothing for a reviewer to notice, which is why the protocol asks for a
written defect and a held card rather than a best guess.

Two boundaries on the protocol are worth knowing:

- **Not every open question is a spec defect.** A question a specification deliberately leaves to
  the implementer is decided by the implementer and recorded as a short decision note, which is
  a much lighter process. The test is whether the question touches frozen semantics at all — any
  meaning a frozen document fixes, and in particular fields of the intermediate representation,
  witness shapes, condition identifiers, fixtures, or a mandate in the statement of work or a
  brief. If it does, it routes as a defect no matter how small it looks.
- **A deviation from a mandate in the statement of work or a brief is not the implementer's to
  decide at all.** Those need the product owner, recorded explicitly as such.

## 6. The fixture corpus, and how a fixture changes

`tests/fixtures/properties/` deserves its own section, because it is the file tree a new
contributor is most likely to want to edit and least likely to be allowed to.

It is the **acceptance fixture corpus**: a set of serialized IR documents — one workflow
definition each, in the extracted intermediate representation, never live LangGraph Python —
each paired with the verdict the validators are supposed to reach on it. It is simultaneously
the validators' specification-by-example, the test engine's input, and a contract surface shared
across tracks, which is why it is vendored (section 4) rather than merely reviewed.

So when a validator's output and a fixture's recorded expectation disagree, you have found
something, and the one move that is not available is changing the fixture so the test passes.
The disagreement is resolved as a decision, in one of two directions:

- **the validator is wrong** — fix the validator; the fixture stands; or
- **the fixture is wrong** — which needs vault-side fixture-review sign-off (the corpus's R-05
  lead review) before anything changes.

Either way the outcome is logged in the fidelity matrix
([FIDELITY-MATRIX.md](https://github.com/Gebra-Tech/gebra/blob/main/docs/governance/FIDELITY-MATRIX.md)),
so the reasoning survives the pull request that produced it.

A fixture revision, when it is the right answer, routes the long way round: a proposal
(a set of bytes, not a description), then sign-off recorded as a decision in the vault, then the
re-vendor commit citing that vault hash, then the corpus lint green. `tools/corpus_reconcile.py`
is the worked example of the first step — it holds a whole ruled revision pass as data, each
edit a before/after pair of a fixture's literal expectation block citing the passage that fixes
its shape, and it refuses to write inside the corpus directory at all. That refusal does not
relax once a ruling lands.

The corpus lint is the last gate:

```bash
python tools/corpus_lint.py
```

Reviewing a change to the corpus asks a narrower question than gating it — not "is the corpus
clean" but "what does this gate say about the files this change touches" — and `--only` answers
that one, taking the output of `git diff --name-only` unchanged:

```bash
python tools/corpus_lint.py --only tests/fixtures/properties/mixed/10-all-properties-pass-healthy-research-pipeline.yaml
```

It is a narrower *report*, never a narrower check: the whole corpus is read exactly as above,
and what that run found is then filtered to the fixtures you named, plus every corpus-wide
finding no single file can own — the per-directory minimums, serial uniqueness, the grand-total
floor, which is where a deletion shows up. So a scoped verdict and a full one are incapable of
disagreeing about a fixture. A path that names no fixture in the corpus stops the run rather
than narrowing the scope quietly; if a change deletes that path, drop it from `--only` and the
corpus-wide rules judge its effect.

That is also how a fixture change is reviewed: the maintainers' `/fixture-review` reaches its
conformance verdict by running this lint rather than by walking a checklist written beside it,
so a review verdict and the CI job's verdict cannot differ. What the skill still reads for
itself is the half no script can compute — the vault decision record, the new vault hash, and
the updated manifest rows that make a revision a routed one.

## 7. Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), with the card identifier where the
work is card-scoped:

```text
<type>(<scope>): <subject> [<CARD-ID>]
```

`feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci` — the scope is lowercase and names the
area, and the subject is a phrase rather than a sentence. Three shapes (the middle one is
re-vendoring.md's own template, placeholder vault hash and all):

```text
feat(ir): canonical JCS emitter [IR-03]
chore(fixtures): re-vendor mixed/04 from vault a1b2c3d [TE-03]
docs(contributing): contributor guide [DOC-19]
```

The card identifier is what ties a commit to the objective and acceptance checklist it was
written against. Board-only commits (`chore(plan): claim DOC-19`) are their own category and
carry no card suffix.

**One trailer exists, and it is not optional where it applies.** Three test trees pin extracted
bytes and digests as golden files. A commit that changes golden bytes under one of them —
documentation inside a golden tree is not a golden, and the guard classifies only non-Markdown
files — must carry a `Golden-Justification:` trailer, in one of exactly two forms: a matrix
extension citing the drift-suite run that justified it, or a ratified change to the intermediate
representation with its version bump and decision record.

```text
Golden-Justification: drift-run=<Actions run id> <substrate pair>
Golden-Justification: DEC-<n> ir_version=<x.y> <what changed>
```

A CI job checks that the trailer is present and well-formed on every commit in the push; whether
the citation actually justifies the diff is a question for review. There is no bypass flag, and
a justified commit does not cover an unjustified one in the same push. Check a pending change
before you push it:

```bash
python tools/golden_guard.py --files <changed paths...> --message "<the commit message>"
```

If you squash-merge, the squashed message is the one the guard judges — keep the trailer in it.

## 8. Open the pull request

The template walks the checklist: the CLA row, the commit format and card link, the provenance
guard, the golden justification, the four gates, tests that execute nothing, and prose that
claims only what the code does. Ticking a box you have not checked is the specific thing it
exists to prevent; leaving one unticked with a sentence saying why is an ordinary review
conversation.

**What runs.** Eighteen CI jobs, on every push and every pull request. Beyond the four gates of
section 2, these are the ones that refuse a change for a reason local `pytest` will not have
told you about:

| Job | Refuses |
|---|---|
| `provenance` | a vendored file whose bytes moved, went missing, or appeared unlisted |
| `honest-claims` | a banned phrase anywhere in repository-authored prose |
| `golden-guard` | a golden-file diff in a commit carrying no well-formed justification |
| `corpus-lint` | a fixture that does not conform to the corpus schema and its per-directory rules |
| `docs` | a documentation example whose output is not what the page shows, or a site build warning |
| `test-matrix` | a failure on any of the twelve tested Python and substrate pairings |

**The honest-claims lint deserves a sentence of its own**, because it surprises people. This
project draws a hard line between what it checks and what it does not. It reads a workflow
*definition* and reports what that definition — its structure and its declared annotations —
establishes, at the strength its claim class licenses; every finding carries that class, and the
three are the whole ladder. `defensible` is decidable over the extracted document alone;
`defensible-a` rests on declared annotations whose truthfulness is trusted rather than checked,
the way a type annotation is; `heuristic` is advisory lint and makes no proof claim. A passing
property carries a structured witness rather than a claim about what the workflow will do at run
time.

Prose that blurs any of those lines is a defect — including copy that renders a finding without
its claim class — so a list of banned phrases is enforced across documentation, docstrings, CLI
output and error messages alike. Run it before you push:

```bash
python tools/honest_claims_lint.py
```

The list is not the whole rule — it is the mechanical part of it. The rule is that a claim in
prose has to be a claim the code demonstrates, and review applies that to sentences no substring
search would catch.

A line that has to quote the wording the list rejects — a page explaining the rule, an error
message naming what it refuses — carries an allow-pragma, and the reason is part of it: a pragma
with no reason is a violation in its own right rather than a silent bypass. This page uses one,
and shows it:

```markdown
<!-- honest-claims: allow: naming what the list rejects, never asserting it -->
Gebra never says that a check "proves termination".
```

Where a pragma may sit relative to the line it exempts is stated by the lint's own failure
message, so that placement rule has one home. The same run is available as data —

```bash
python tools/honest_claims_lint.py --format json
```

— which prints every violation and, beside them, every line a pragma exempts together with the
reason given. That second half is there so that a reviewer working past the substring list is
reading the exemptions this lint granted rather than deciding for themselves which ones count.

**Then review.** Every pull request except a board-only plan commit needs the code owner's
review, and the maintainer is the one who merges. Changes to an area with a frozen contract —
the intermediate representation and its canonical form, extraction, the validators and their
condition identifiers, or any path that has to be shown not to execute a workflow — get a
specialist pre-review against the governing specification before that human review, so a factual
disagreement with a frozen document arrives as a citation rather than as an opinion.

## A walkthrough: the card that produced this page

The page you are reading is the output of one card, and its history is a worked example of
everything above.

**The card.** `DOC-19 — Contributor guide`, on the documentation track's board, estimate `M`. Its
objective names six topics — the spec-defect protocol, provenance rules, the fixture-revision
flow, the CLA, conventional commits, and the boards-and-gate workflow — which is why this page
has the sections it has, and it leaves the structure and the question of how much of
CONTRIBUTING.md to supersede to whoever implements it. That is the "decisions to implementer"
part of a card: latitude, stated as latitude.

**The gate.** Its prerequisites were three cards: `DOC-01` (the documentation toolchain and the
executable-examples harness), `GOV-09` (the contribution governance operations — the CLA record
and the provenance guard) and `TOOL-01` (the tooling validation that proved `/next-task` really
refuses a blocked pick). All three were `done`, and no gate token appeared in the list, so the
rule from section 3 returned READY with nothing unmet. Had any one of them been `in-review`, the
answer would have been BLOCKED with that card named, and the correct response would have been to
work on something else. (Run the rule over the card *today* and the first condition fails
instead: its own status is no longer `todo`.)

The dependency edges are not bureaucracy here: this page could not have been written before
`DOC-01`, because it needs the harness that runs its two examples; nor before `GOV-09`, because
sections 1 and 4 describe a CLA record and a guard that card created; nor before `TOOL-01`,
because section 3 describes a refusal that card observed rather than assumed.

**The claim.** `status: todo` became `status: in-progress` with `claimed_by` recording who and
when, in its own `chore(plan): claim DOC-19` commit.

**The work.** This page, plus a test module that holds it to the things it describes: the guard's
four failure classes read off the guard's own code, the readiness rule against the plan's
definition of it, the CI job table against the workflow file, the banned-phrase lint run over the
page on every test run, and — where the private repository happens to be checked out beside this
one — the card's own prerequisites and their statuses, so the paragraph above cannot go stale
without a test saying so.

**The commit.** `docs(contributing): contributor guide [DOC-19]`. No golden file is touched, so no
justification trailer applies.

**The finish.** The acceptance boxes are checked only for what was actually demonstrated, the
artifacts are recorded on the card, and the card moves to the board's `Done` section. Its status
is now `done`, which is terminal: a defect in this page is a new card, not a reopening of this
one.

## Where to ask

- **A question about the code** — open a [GitHub issue](https://github.com/Gebra-Tech/gebra/issues).
- **A question about whether something is a spec defect** — ask in the issue; that determination
  is a maintainer's, and section 5 is the shape of the answer.
- **The CLA, or anything to do with signing** — `gebra.dev@gmail.com`.

If this page did not answer a question you had to ask anyway, that is worth an issue too. It is
meant to be the page that makes the second question unnecessary.
