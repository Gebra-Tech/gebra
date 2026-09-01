# Install and compatibility

Two questions, and one page for both. **Can I run gebra here?** — what installs, what is
tested, and what the package does when it finds a substrate nobody has tested it against.
And **what does a version change mean?** — for the substrate under you, for gebra itself,
and for the V.S.F.E label on the snapshots you have already recorded.

Nothing on this page is hand-maintained prose about version numbers. The matrix below is the
one CI installs, checked cell by cell against the packaging metadata and against the
classifier `gebra.extract()` actually calls; every transcript is produced by the block above
it, executed in CI.

## Install

### There is no package index yet

`pip install gebra` does not work. The first published release and this repository's public
launch are one step, and neither has happened — the declared version is `0.0.1.dev0`. Until
then gebra installs from a checkout, which is how every contributor already runs it.

```bash
git clone https://github.com/Gebra-Tech/gebra.git
cd gebra
pip install .
```

Those three lines are the only commands on this page CI does not run. The build they perform
is run, though, one step apart: `pip install .` asks the pinned `hatchling` backend for a
wheel and installs it, and the `build` CI job builds a wheel through that same pinned backend
and installs it into an empty environment on every push. The two routes below are the ones
with a job behind them.

### The distribution, into a clean environment

What the `build` job does — build the wheel and the sdist the release workflow would ship,
then install the wheel into a virtual environment holding nothing else:

```bash
uv build --out-dir dist
```

```bash
python -m venv /tmp/wheelcheck
/tmp/wheelcheck/bin/pip install --no-cache-dir dist/*.whl
```

This is the closest thing to installing a published package, and it is the route that catches
a package which only worked because the repository was on `sys.path`.

### A development environment

The repository is managed with [uv](https://docs.astral.sh/uv/), and `uv.lock` pins the whole
resolution — one substrate, the development extras, the toolchain:

```bash
uv sync --extra dev --frozen
```

The pip route to the same set stays supported and is exercised by its own job:

```bash
pip install -e ".[dev]" -c tools/matrix-constraints.txt
```

`tools/matrix-constraints.txt` is derived from `uv.lock` and pins the *non-substrate* half of
the resolution — the development toolchain and the other locked dependencies — so a pip
install does not float with the day's index. It deliberately constrains nothing the
compatibility cells pin differently, which is why the next command still decides its own
substrate.

### One compatibility cell, reproduced

Every tested substrate pair is an installable extra. Cell 3 — the newest of the three — is
what the acceptance-scenario job installs:

```bash
pip install -e ".[dev,compat-cell-3]" -c tools/matrix-constraints.txt
```

Swap `compat-cell-3` for `compat-cell-1` or `compat-cell-2` for the older pairs. The bare
`compat-test` extra is cell 3 under the name the specification uses.

### Which job runs which command

| Command | CI job |
|---|---|
| `uv build --out-dir dist` | `build`, `readme-quickstart` |
| `python -m venv /tmp/wheelcheck` + `/tmp/wheelcheck/bin/pip install --no-cache-dir dist/*.whl` | `build` |
| `uv sync --extra dev --frozen` | `lint`, `typecheck`, `test-locked`, and four more |
| `pip install -e ".[dev]" -c tools/matrix-constraints.txt` | `pip-editable`, `docs`, `test-matrix-pre` |
| `pip install -e ".[dev,compat-cell-N]" -c tools/matrix-constraints.txt` | `dod`, and the twelve `test-matrix` cells |

`tests/docs/test_install_and_compatibility.py` holds every shell command on this page to that
table: a command here that no job runs fails the build, and the three-line checkout block
above is the one declared exception.

### What comes with it

gebra's own metadata, read from the installed distribution:

<!-- gebra:example id=what-the-install-brings -->
```python
from importlib import metadata

print("gebra          ", metadata.version("gebra"))
print("requires-python", metadata.metadata("gebra")["Requires-Python"])
print()
for requirement in metadata.requires("gebra") or ():
    if "extra ==" in requirement:
        continue
    print(requirement)
```

<!-- gebra:output id=what-the-install-brings -->
```text
gebra           0.0.1.dev0
requires-python >=3.10

langchain-core<2.0,>=1.0
langgraph<2.0,>=1.0
networkx>=3.0
pydantic<3,>=2.11
rich>=13.8
tomli>=2; python_version < '3.11'
typer>=0.27
```

`langgraph` and `langchain-core` are ordinary required dependencies: gebra reads their
builder, compiled-graph and `Runnable` surfaces to extract an IR, so an install without them
would have nothing to read. It never *runs* anything it reads — no node function, router,
tool or model is called and no connection is opened — but the packages have to be importable.

## What installs, and what is tested — two different questions

The dependency ranges above are the **installability envelope**. They are what pip enforces,
and they are wide on purpose:

| Axis | Declared | Where it comes from |
|---|---|---|
| Python | `>=3.10` | `requires-python`; langgraph 1.x dropped 3.9 |
| `langgraph` | `>=1.0,<2.0` | the 1.x line's no-breaking-change window |
| `langchain-core` | `>=1.0,<2.0` | the same, with the effective floor riding langgraph's own pin |

An install inside those ranges is an install pip will perform. It is not thereby an install
anyone has run the suite against, and gebra never claims it is. The **compatibility promise**
is the narrower statement — *these combinations are the ones the suite runs against* — and it
is a matrix of *pairs*, because independent ranges are not resolvable here: langgraph pins its
own `langchain-core` floor and moves that floor in patch releases, so "any 1.x with any 1.x"
describes combinations that cannot be installed together.

### The tested matrix

Four Python minors × three pair cells = **12 blocking CI cells**, plus one non-blocking
early-warning cell = 13. Every blocking cell runs `ruff check`, `ruff format --check`,
`mypy --strict` and the whole test suite; a red one blocks the release.

| Cell | `langgraph` | `langchain-core` | `pydantic` (transitive) |
|---|---|---|---|
| 1 | `1.0.10` | `1.1.3` | `2.13.4` |
| 2 | `1.1.10` | `1.3.3` | `2.13.4` |
| 3 | `1.2.10` | `1.5.3` | `2.13.4` |

Python: **3.10, 3.11, 3.12, 3.13**, all four against all three cells.

Those are exact pins, and they are frozen — the tested matrix stopped moving on its own at
the freeze that closed this phase's compatibility work, and each pin now changes only through
the extension or cap procedure further down. `pydantic` is pinned per cell even though the
three agree today: it is a transitive of langchain-core, so it is a property of each cell's
resolution rather than an axis of its own. Two langgraph releases inside the declared range —
`1.1.7` and `1.2.3` — are yanked and are excluded by these pins rather than by the range: a
version range cannot exclude a point version.

The 13th cell installs the newest prerelease of both packages (`pip install --pre`) on the
newest tested Python and is allowed to fail: it exists to see a change coming, not to gate a
release.

### The bands the runtime check compares against

The pins are what CI installs. The check inside `gebra.extract()` cannot compare an install
against one patch release and call everything else untested, so it reads each cell as a band.
The first two are the bands the compatibility promise names outright — langgraph 1.0.x with
core 1.0–1.1, and 1.1.x with core 1.2–1.3. The third the promise names as "1.2.latest", which
a runtime check has no patch-exact value to compare against, so this build reads it as the
whole 1.2.x line — the boundary the next ceiling extension would move anyway:

| Cell | `langgraph` | `langchain-core` |
|---|---|---|
| 1 | `>=1.0, <1.1` | `>=1.0, <1.2` |
| 2 | `>=1.1, <1.2` | `>=1.2, <1.4` |
| 3 | `>=1.2, <1.3` | `>=1.4.7, <2.0` |

Python is compared as a minor version against the four tested ones, and against the `>=3.10`
floor. Prerelease and local suffixes are discarded before the comparison — `2.0.0a1` is read
as `2.0.0`, which is the conservative answer at the range boundary this section is about,
since an alpha of the next major already carries that major's surface.

A langgraph inside one cell's band paired with a langchain-core from another cell's band is
**not** a tested pairing, even though both packages are individually inside the envelope.
That is what "the promise is a pair matrix" means, and it is the case the next section's
third row shows.

## Which class an install lands in

Every install is exactly one of three things. The classifier is public, and this is it
running:

<!-- gebra:example id=the-three-compatibility-classes -->
```python
from gebra.extraction import SubstrateVersions, classify_substrate


def install(python, langgraph, langchain_core):
    return SubstrateVersions(
        python=python,
        langgraph=langgraph,
        langchain_core=langchain_core,
        langgraph_raw=".".join(str(part) for part in langgraph),
        langchain_core_raw=".".join(str(part) for part in langchain_core),
    )


cases = [
    ("3.11, langgraph 1.2.10, core 1.5.3", install((3, 11), (1, 2, 10), (1, 5, 3))),
    ("3.10, langgraph 1.0.10, core 1.1.3", install((3, 10), (1, 0, 10), (1, 1, 3))),
    ("3.13, langgraph 1.0.10, core 1.5.3", install((3, 13), (1, 0, 10), (1, 5, 3))),
    ("3.14, langgraph 1.2.10, core 1.5.3", install((3, 14), (1, 2, 10), (1, 5, 3))),
    ("3.13, langgraph 2.0.0, core 1.5.3 ", install((3, 13), (2, 0, 0), (1, 5, 3))),
    ("3.9,  langgraph 1.2.10, core 1.5.3", install((3, 9), (1, 2, 10), (1, 5, 3))),
]
for label, versions in cases:
    print(f"{label}  ->  {classify_substrate(versions).value}")
```

<!-- gebra:output id=the-three-compatibility-classes -->
```text
3.11, langgraph 1.2.10, core 1.5.3  ->  tested
3.10, langgraph 1.0.10, core 1.1.3  ->  tested
3.13, langgraph 1.0.10, core 1.5.3  ->  in-range-untested
3.14, langgraph 1.2.10, core 1.5.3  ->  in-range-untested
3.13, langgraph 2.0.0, core 1.5.3   ->  out-of-range
3.9,  langgraph 1.2.10, core 1.5.3  ->  out-of-range
```

| Class | What it is | What gebra does |
|---|---|---|
| `tested` | a matrix cell's pair, on a tested Python | nothing — the conforming case is silent |
| `in-range-untested` | everything inside the declared ranges that is not a cell: a cross-cell pairing, a minor line the bands have not reached, or a Python above 3.13 | warns `GebraVersionWarning` once per process |
| `out-of-range` | `langgraph` or `langchain-core` outside `>=1.0,<2.0`, or a Python below the declared 3.10 floor | extracts best-effort; every envelope carries the version fact |

The two `in-range-untested` rows in the transcript are the two shapes worth recognising. Row
three is a **cross-cell pairing** — langgraph from cell 1, langchain-core from cell 3 — and
row four is a **Python above the tested ceiling**. Neither is an error; both are a statement
that nobody has run the suite on what you have.

A Python *below* the floor is different: `3.9` reads as out-of-range, the same posture the two
packages get, rather than as merely untested. That last row is this build's reading rather
than something the specification spells out — the specification gives the two packages'
ranges and is silent on a sub-floor Python — and the symmetry is the reason for it. The
declared floor is an installability requirement pip enforces, so reaching the row at all takes
an install that went around pip.

### Checking an install from your own code

`read_installed_versions()` reads the two distributions' metadata — never importing either
package — and `classify_substrate()` places the triple:

<!-- gebra:example id=checking-your-own-install -->
```python
from gebra.extraction import CompatClass, classify_substrate, read_installed_versions

versions = read_installed_versions()
compat = classify_substrate(versions)

# `versions` also carries the three version strings themselves. Printing them here would
# print thirteen different transcripts, because CI runs this page's examples in every cell.
print("inside the declared ranges:", compat is not CompatClass.OUT_OF_RANGE)
```

<!-- gebra:output id=checking-your-own-install -->
```text
inside the declared ranges: True
```

`versions.python` is the `(major, minor)` pair the check reads, `versions.langgraph_raw` and
`versions.langchain_core_raw` are the two version strings as the distributions report them,
and `compat.value` is one of the three words in the table above. A project that wants the
stronger condition asserts `compat is CompatClass.TESTED`.

## `GebraVersionWarning`

The check runs on the **first `gebra.extract()` call in a process**, and nothing observable
happens at import: `import gebra` never warns and never fails on version grounds, whatever is
installed. (Importing `gebra.extraction` does resolve the classification quietly, for a
reason its own module records; no warning, no exception and no envelope field turns on when
that happens.) Here the check is firing, on a simulated cross-cell pairing:

<!-- gebra:example id=the-version-warning -->
```python
import warnings

from gebra.extraction import SubstrateVersions, compat, extract
from tests.sample_workflows import travel_booking

# Simulating an install this machine does not have. Application code never does this — the
# check reads the two installed distributions' own metadata.
compat.read_installed_versions = lambda: SubstrateVersions(
    python=(3, 13),
    langgraph=(1, 0, 10),
    langchain_core=(1, 5, 3),
    langgraph_raw="1.0.10",
    langchain_core_raw="1.5.3",
)
compat.reset_version_check_cache()

agent = travel_booking.build_travel_booking_agent()
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    first = extract(agent)
    second = extract(agent)

print("class            ", compat.check_version_once().compat.value)
print("warnings raised  ", len(caught))
print("category         ", caught[0].category.__name__)
print("extraction  #1   ", first.graph_version())
print("extraction  #2   ", second.graph_version())
print("envelope warnings", first.warnings, second.warnings)
print("node bodies run  ", travel_booking.TRIPPED)
print()
print(caught[0].message)
```

<!-- gebra:output id=the-version-warning -->
```text
class             in-range-untested
warnings raised   1
category          GebraVersionWarning
extraction  #1    sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
extraction  #2    sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
envelope warnings () ()
node bodies run   []

gebra has not been tested against this exact substrate pairing — python 3.13, langgraph 1.0.10, langchain-core 1.5.3 — though every one of them is within gebra's declared version ranges; extraction is unverified against this pair (VERSION-COMPAT.md §4)
```

Five things that transcript pins.

**It is a warning, not a failure.** The classification changes nothing about extraction, so
both calls returned, at the digest this workflow has on every tested cell, and the envelope
carries no extraction warning at all — being untested is a fact about gebra's testing, not a
defect in the document.

**Once per process, not once per call.** Two `extract()` calls, one warning. A pipeline that
extracts a hundred workflows does not print a hundred lines.

**It is a plain `warnings` category.** `GebraVersionWarning` subclasses `UserWarning` and is
never raised by gebra itself, so the standard `warnings` filters apply to it unchanged.

**The message names all three versions**, so a log line is enough to reconstruct which
pairing produced it. The `VERSION-COMPAT.md §4` citation at the end points at the
repository-internal specification that rules the supported ranges; it is not a page on this
site.

**Nothing was executed.** The ledger is empty: the sample agent's node bodies record
themselves and raise if anything calls them.

### Turning it into an error, or filtering it away

Both directions are the ordinary `warnings` ones:

<!-- gebra:example id=treating-the-warning-as-an-error -->
```python
import warnings

from gebra.extraction import GebraVersionWarning, SubstrateVersions, compat, extract
from tests.sample_workflows import travel_booking

compat.read_installed_versions = lambda: SubstrateVersions(
    python=(3, 13),
    langgraph=(1, 0, 10),
    langchain_core=(1, 5, 3),
    langgraph_raw="1.0.10",
    langchain_core_raw="1.5.3",
)

agent = travel_booking.build_travel_booking_agent()

compat.reset_version_check_cache()
warnings.filterwarnings("error", category=GebraVersionWarning)
try:
    extract(agent)
except GebraVersionWarning as error:
    print("raised           ", type(error).__name__)
    print("a UserWarning    ", isinstance(error, UserWarning))

compat.reset_version_check_cache()
warnings.filterwarnings("ignore", category=GebraVersionWarning)
envelope = extract(agent)
print("filtered away, and extraction still returns:", envelope.graph_version())
print("node bodies run  ", travel_booking.TRIPPED)
```

<!-- gebra:output id=treating-the-warning-as-an-error -->
```text
raised            GebraVersionWarning
a UserWarning     True
filtered away, and extraction still returns: sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
node bodies run   []
```

A project that wants an untested substrate to stop the build adds
`filterwarnings = ["error::gebra.extraction.GebraVersionWarning"]` to its pytest
configuration, or the `warnings.filterwarnings` line above to whatever runs first. A project
that has decided its pairing is fine silences it the same way with `"ignore"`. gebra takes no
position on which; it reports the fact once and gets out of the way.

`reset_version_check_cache()` in those two blocks is the one call above that a real program
never makes: it clears the per-process memo so a page can show two independent first calls.

## Out of range: best-effort, and the fact rides every envelope

Outside the declared ranges, the treatment is not a Python warning at all. Extraction
proceeds, and the version fact is attached to **every** envelope it produces as a structured
`unsupported-construct` extraction warning — which `gebra verify` must surface, and which no
`warnings` filter can suppress:

<!-- gebra:example id=an-out-of-range-substrate -->
```python
import warnings

from gebra.extraction import SubstrateVersions, compat, extract
from tests.sample_workflows import travel_booking

compat.read_installed_versions = lambda: SubstrateVersions(
    python=(3, 13),
    langgraph=(2, 0, 0),
    langchain_core=(1, 5, 3),
    langgraph_raw="2.0.0",
    langchain_core_raw="1.5.3",
)
compat.reset_version_check_cache()

agent = travel_booking.build_travel_booking_agent()
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    first = extract(agent)
    second = extract(agent)

print("class              ", compat.check_version_once().compat.value)
print("python warnings    ", len(caught))
print("envelope warnings  ", len(first.warnings), len(second.warnings))
print()
[warning] = first.warnings
print("code   ", warning.code.value)
print("node   ", warning.node)
for key, value in warning.detail.items():
    print(f"  {key:15} {value!r}")
print()
print(warning.message)
```

<!-- gebra:output id=an-out-of-range-substrate -->
```text
class               out-of-range
python warnings     0
envelope warnings   1 1

code    unsupported-construct
node    None
  construct       'substrate-version'
  location        {}
  why             'installed substrate is outside the declared >=1.0,<2.0 range'
  ir_partial      False
  python          '3.13'
  langgraph       '2.0.0'
  langchain_core  '1.5.3'

the installed substrate is outside gebra's supported version range (langgraph 2.0.0, langchain-core 1.5.3, python 3.13); extraction proceeded best-effort and is unverified (VERSION-COMPAT.md §1, §4)
```

The two counts on the second and third lines are what this build does with an out-of-range
install. **No `GebraVersionWarning` fires** — not even once; the class that warns is
`in-range-untested`, and an out-of-range fact travels in the envelope instead. **Both
envelopes carry the record**, because an envelope describes one extraction, and hiding a true
version fact from the second extraction because the first already reported it would make that
envelope less honest rather than less noisy.

`ir_partial` is `False` and `location` is empty on purpose, and both are statements about
*this record*. The version fact itself dropped nothing from the document, and "where" has no
honest answer when the subject is the installed packages rather than a node, an edge or a
state key. Neither is a completeness verdict on the extraction: a best-effort run against an
out-of-range substrate can also emit records whose `ir_partial` is `True`, and this one
happens to emit none.

## When the substrate moves

langgraph ships patches weekly to fortnightly and langchain-core faster still, so the tested
matrix is behind the index most of the time. That is expected, and it has a procedure rather
than a promise.

**A new release is tested before it is claimed.** The drift suite — twelve conformance tests
over the substrate surfaces extraction reads, run once per cell — is what decides. Green
against the candidate pins, and the matrix extends to include them, in one change that also
carries the CHANGELOG entry citing the run that justified it. Red, and the tested ceiling is
capped at the last green pair and a version-gap issue is opened; the cap and the issue land in
the CHANGELOG too. No assertion is weakened on either path — an assertion downgrade is a
specification change, not a repository edit.

**The pins live in the packaging metadata**, in the `compat-cell-{1,2,3}` extras of
`pyproject.toml`, so "which substrate is tested" and "which substrate CI installs" cannot
disagree: there is nowhere else for a cell's substrate to come from.

**A 2.0 major is watched for, not planned around.** `<2.0` is the boundary of the vendor's
own no-breaking-change window for the unprefixed surfaces extraction reads, and the 2.0 line
is documented to remove a schema accessor the drift suite already has a test for. A
prerelease appearing triggers an immediate run of the `--pre` cell and a review of the
supported range — a decision, taken then, with the run's evidence in front of it. Nothing
here forecasts its outcome or its date.

**What this means for you.** If your pairing is `tested`, nothing. If it is
`in-range-untested`, you are running a combination whose suite nobody has run — the extraction
is the same code either way, and the honest reading of the warning is "unverified here", not
"broken here". If you want evidence for your own pairing, the reproducible route is the cell
install above with your versions substituted, plus the repository's own suite; getting that
pairing *into* the tested matrix is a ceiling extension, and it starts with the drift suite
against your pair.

## The version numbers you will meet

Four different things are called a version around gebra, and only one of them is about your
workflow.

| Number | Example | What it versions | What moves it |
|---|---|---|---|
| The package version | `0.0.1.dev0` | gebra itself | a gebra release |
| The substrate versions | `langgraph 1.2.10` | what gebra reads | upgrading your own dependencies |
| `ir_version` | `1.0` | the IR *format* | a ratified change to the IR schema |
| The V.S.F.E label | `1.2.3.3` | **your workflow definition** | your edits |

`graph_version` — the `sha256:…` digest in the transcripts above — is the fifth thing and is
not a version number at all: it is the content identity of one extracted document. Two
extractions of an unedited workflow produce the same digest; any edit that changes the
document's canonical form produces a different one. [The IR, node identity and
`graph_version`](../concepts/ir-and-graph-version.md) is the long form.

## V.S.F.E: versioning your own workflow

A snapshot's label is four independent counters, `V.S.F.E`. **S** counts topology changes,
**F** node and contract changes, **E** state-schema changes. **V** is yours: gebra carries it
through and never moves it. Here are seven consecutive edits to one agent, each run through
the comparator that assigns the labels:

<!-- gebra:example id=which-edit-moves-which-counter -->
```python
from gebra import extract
from gebra.versioning import Component, Version, changed_components, next_version
from tests.sample_workflows import travel_booking_evolution as evolution

label = Version.parse("1.0.0.0")
previous = extract(evolution.EVOLUTION[0].build()).ir
for stage in evolution.EVOLUTION[1:]:
    working = extract(stage.build()).ir
    moved = changed_components(previous, working)
    counters = " ".join(part.value for part in Component if part in moved)
    label = next_version(label, previous, working)
    print(f"{label}  {counters:5}  {stage.summary}")
    previous = working

print()
print("an unedited workflow moves ", changed_components(previous, previous) or "no counter")
print("and keeps its label        ", next_version(label, previous, previous))
print("node bodies run            ", evolution.TRIPPED)
```

<!-- gebra:output id=which-edit-moves-which-counter -->
```text
1.0.0.1  E      Σ gains the optional graph-input key seat_preference; nothing consumes it
1.1.1.1  S F    contracted join_waitlist node, a waitlist label on route_booking, END wiring
1.2.1.1  S      route_availability gains a waitlist label to the existing join_waitlist node
1.2.1.2  E      Σ drops itinerary while two contracts still declare the write and the read
1.2.1.3  E      availability is redeclared list[str] while four contracts still read it
1.2.2.3  F      replan loses its variant annotation, the carrier both cycles run through
1.2.3.3  F      check_booking's effects gain billable, entering the P-06 trigger set

an unedited workflow moves  no counter
and keeps its label         1.2.3.3
node bodies run             []
```

Each line's description is the evolution sequence's own summary of the edit, which is why the
last one names a property: `check_booking`'s declared effect tuple gained a tag that the
[P-06 `effect-safety`](../validators/p06-effect-safety.md) trigger set contains. That is a
statement about the *edit*, not a verdict — nothing in this transcript runs a validator, and
whether that tag raises a finding depends on where the node sits, which P-06 decides on its
own page.

Four rules are visible in that transcript.

**One edit can move two counters.** Adding a node moves S *and* F — the topology gained a
vertex and the contract set gained a member — which is why the second row goes from `1.0.0.1`
to `1.1.1.1`. Renaming a node is the same case, because a rename is a new identity rather than
a modification of an old one.

**Bumps do not reset anything to their right.** `1.2.1.3` with a contract change becomes
`1.2.2.3`, not `1.2.2.0`. The counters are independent tallies of "how often has this domain
changed", not positions in a precedence order.

**The comparison is by canonical content.** Re-extracting an unedited workflow moves nothing,
and neither does an edit that leaves the canonical document unchanged — listing nodes in
another order, or writing a state value in its long form. It is the same normalisation
`graph_version` is taken over, so the two agree by construction: two documents with the same
digest move no counter.

**A bump is not a verdict.** The label says which domain of your definition changed and how
often. It does not say what changed — that is what a diff report is for — and it does not say
whether the change was safe: classifying an evolution as a safe extension or a breaking change
is property P-12 `evolution-safety`, which is outside this release, and every diff says so in
the slot where that classification would go. [Snapshot, diff and
evolution](snapshot-diff-and-evolution.md) walks the same sequence with the diff reports
alongside, and carries the counter-by-counter table of which IR field moves which component.

## What a gebra release can move, and what it cannot

**Your stored labels are yours.** A snapshot's file name is its V.S.F.E label, and gebra never
renumbers one. Upgrading gebra does not renumber a store.

**A digest binds a document, not an extractor.** `graph_version` is defined over the canonical
form of an IR document, so any conforming implementation computing it over the *same document*
gets the same string. It stays comparable across releases because of a second rule: a change
to the canonicalization itself is digest-breaking for existing documents and requires an
`ir_version` bump, and `ir_version` is inside the hashed payload. What is not promised by any
of that is that a later extractor reads the same *workflow* into the same document — a
substrate that
starts reporting a field differently would change the document and therefore the digest. That
is exactly the gap the drift suite and the tested matrix exist to watch, and it is why they
compare extracted documents against committed goldens once per cell.

**`ir_version` is a format migration, and a different thing from your workflow's version.**
The IR schema has its own version — `1.0` in this release, and `1.1` for a document holding a
router whose targets are decided at run time, which this build extracts and every downstream
consumer in it then declines: verify, snapshot, diff, the diagram emitter and the freshness
check each refuse it by name. A change to that number is a change to the *format*; a V.S.F.E bump is a
change to a *workflow*. The two are never conflated, and an `ir_version` change moves no
V.S.F.E counter.

## Where this page is checked

Every transcript above is produced by the code block above it, executed in a fresh interpreter
in CI, and compared byte for byte against what the page shows — the mechanism is
[executable examples](../contributing/executable-examples.md). Beyond that,
`tests/docs/test_install_and_compatibility.py` holds the page's prose to its sources: every
shell command against the CI workflow that runs it, the declared dependency ranges and
`requires-python` against the packaging metadata, the matrix's pins against the
`compat-cell-N` extras, the cell counts against the workflow's own matrix, every band in the
runtime-check table against the classifier itself in both directions — a pairing the table
calls tested that the classifier does not, or the reverse, fails — the compatibility-class
table against the enumeration, the warning message against the function that builds it, the
V.S.F.E transcript's labels and counters against the evolution sequence's recorded
expectations, the P-12 deferral against the marker a real diff carries, and the effect tag
the last transcript row names against that stage's own declared contract. Where the development-process repository is checked out beside this one, the
same module reconciles the ranges, the pins, the cell counts and the freeze citation against
the specification that rules them. A statement here that stopped being true fails the build
rather than aging quietly.
