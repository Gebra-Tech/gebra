"""WA-07 tripwire for the fixture and generation paths: no substrate import, no socket, no
execution.

The corpus exists so that the validators can be tested "without importing langgraph or
executing any Python" (``schema.yaml``), and the card that built the loader asks for that to
be *test-proven* rather than reviewed. It is proven the only way a transitive import can be:
in a fresh interpreter where importing a substrate package raises and where creating a socket
or resolving a name raises, the whole load path runs — import :mod:`gebra.testing`, load all
sixty vendored fixtures, compose every ``expected:`` block that composes, run the corpus lint
end to end, and (since TE-02) run the golden harness, which **executes** every registered
validator over every fixture inside the guard. That last leg is the qualitative change: the
validators were already in the import closure, and are now run there.

Since TE-08 the child covers a **second** path with the same guard: hypothesis generation.
:mod:`gebra.testing.strategies` builds ``ir_version`` 1.0 models out of generated primitives,
and the child drives it under ``@given`` and runs P-01 over every draw — so the claim now
reaches IR that nothing in the corpus authored. It joins this file rather than getting a
parallel tripwire for the reason TE-01/TE-02/TE-03 each did: the static scans below run over
exactly the closure the child reports, so a module joining the child joins the scans with it.
Hypothesis joins pydantic (through ``gebra.ir``) and PyYAML (through the fixture loader) as
third-party code inside the guarded interpreter; the static scans below are scoped to
``gebra.*``/``tools.*`` and so read none of the three, and the blocker list is what says they
reach no substrate.

Since TE-10 there is a **third**, and it is the widest input surface in the repository:
:mod:`gebra.testing.mutations` rewrites a generated workflow into one that breaks a contract or
advisory property at exactly one point, and the child runs P-04, P-06 and P-08 over both halves
of every mutation. What that adds over the generation leg is *adversarial* input — a dangling
compensation hook, a read of a key no node writes, a declared determinism claim on a node tagged
as calling a remote provider — reaching the three validators under the guard. A validator that
tried to *resolve* any of those (import a module named by a hook, look up a provider, reach a
network) would be caught here rather than in production: by a blocker where the target is a
substrate package or a socket, and by the static scans below where it is anything else, since
those run over exactly the closure this child reports.

Since TE-09 the mutation path has a **structural** half, and it is the widest *graph* input the
guard has seen: :data:`~gebra.testing.mutations.WELL_FORMEDNESS_OPERATORS` produce documents
whose references resolve to nothing, and
:data:`~gebra.testing.mutations.TERMINATION_OPERATORS` produce documents carrying a cycle whose
only declared termination witness has just been removed. P-01 and P-02 run over both halves of
every one. What that adds over the contract half is two validators that read the *graph* rather
than a contract, on exactly the input where a validator would be tempted to resolve something —
P-01 spells an unresolved reference back into a report rather than looking it up, and P-02 hands
every router's declared ``condition`` to the §3 recognizer, which is a regular expression over
declared text and must stay one. The abort-capped census and the dominator pass run here too.

Since TE-04 there is a leg that runs the *aggregation* rather than a
validator: ``tools.corpus_green`` calls :func:`gebra.verify.verify` — thirteen properties, the
markers, the §2.2 gate derivation — and then re-reads every ``expected:`` block that does not
compose to attribute it, composing a ``PR-1`` projection out of two of them. So the run-level
path and the attribution pass are both inside the guard, and the four clause ids, the number of
properties ``verify()`` answered and the set of causes derived are all asserted, not just
counted. The leg is run **without** a fidelity matrix (``matrix_path=None``), which changes
only whether an R3.2 shortfall reads as routed — nothing this file asserts — and which is what
keeps a governance document out of a WA-07 tripwire's failure modes.

The tripwire follows the pattern VAL-13 ratified for the envelope
(``tests/verify/test_base.py::test_importing_the_envelope_pulls_in_no_langgraph``), point for
point, because each point is there for a reason this path shares:

* **attempts are recorded before raising**, so a ``try: import … except ImportError: pass``
  anywhere on the path still fails the run — and the path itself imports PyYAML exactly that
  way (``gebra.testing.fixtures._yaml_module``), so this is not hypothetical;
* **``getaddrinfo`` is patched** alongside ``socket.socket``, because DNS resolution is
  network activity that precedes socket creation;
* **the raiser subclasses the real socket class in ``__new__``**, so a future
  ``class SSLSocket(socket.socket)`` anywhere in the closure stays *definable* and only
  *instantiation* trips;
* **both halves have a negative control.** A blocker nobody trips proves nothing, so the
  import blocker, the swallowed-import path, the socket raiser and the DNS raiser each have a
  test that deliberately trips them and asserts the tripwire fired.

The scanned source list is not hand-maintained: the guarded child reports the file of every
``gebra.*`` and ``tools.*`` module that the load path actually pulled in, and the static scans
below run over exactly those — so a module joining the load path joins the scan with it.

``source_snippet`` is the third hazard. ``schema.yaml`` calls it "illustrative LangGraph
Python … NEVER executed", and the load path never compiles, imports or evaluates it — scanned
statically here, and behaviourally in ``tests/testing/test_fixture_loader.py``, which loads a
fixture whose snippet would raise on execution.

**Residuals, named rather than implied.** The guarded child blocks neither ``subprocess`` nor
file writes, so both are reviewed rather than tested — and the two are not in the same state:

* **``subprocess``** is absent from the closure, and the static ``_HAZARDOUS_IMPORT`` scan
  below is what keeps it absent.
* **The harness executes a callable resolved from a process-global registry** (TE-02), so the
  guarded run proves hermeticity for *what is registered* — today all five wedge validators,
  and whatever later cards register. The bound is
  :func:`gebra.verify.register_validator`, which refuses every non-wedge slug; the claim is
  not that an arbitrary callable would be safe. Since TE-04 :func:`gebra.verify.verify`
  reaches that same registry inside the guard, and it differs from the harness in one way that
  matters here: it **swallows** whatever a validator raises, into a §2.4 tool-error report. So
  an ``AssertionError`` from one of this file's own raisers would not surface as a crash on
  that path. Two things cover it — ``attempts`` is recorded *before* the raise, by design, and
  the leg asserts that ``verify()`` answered thirteen properties rather than degrading. Both
  are now load-bearing rather than incidental.
* **File writes are not absent.** Since TE-03 the closure contains ``tools.corpus_reconcile``,
  which writes a *candidate* corpus (``shutil.copytree`` + ``Path.write_text``) — the one
  bounded write path in the fixture tooling. Nothing here bounds it: ``shutil`` is not in
  ``_HAZARDOUS_IMPORT``'s list (correctly — it reaches no interpreter), and the bound is that
  module's own ``_refuse_vendored``, tested exhaustively in
  ``tests/testing/test_corpus_reconcile.py`` rather than here. The guarded child exercises only
  that module's read-only half (``audit``); ``emit`` is statically scanned but never run under
  the guard. That costs nothing for *this* file's claim, because ``shutil`` is imported at
  module scope: the import closure the child reports is the same either way.
* **``hypothesis`` is in the guarded interpreter** since TE-08, and it is neither a ``gebra.*``
  nor a ``tools.*`` module, so the static scans do not read it — the dynamic half is what
  covers it, and it is under the blockers like everything else. **It writes**, and the flag that
  looks like it stops that does not: ``database=None`` switches off the example database, but
  hypothesis 6.x separately maintains a constants/charmap cache under ``<cwd>/.hypothesis``
  (``storage_directory``) that is written regardless, and populates it by reading and
  ``ast.parse``-ing the source of every local module it has not seen. Both are gitignored
  caches and neither reaches an interpreter — parsing is not evaluation, and the scan is the
  same one hypothesis runs in every suite in this repository — but this file's value is that its
  residual list is exact, so the write is named here rather than absorbed into TE-03's. The
  mutation leg (TE-10) rides the same residual and adds no new one: it imports nothing
  hypothesis has not already pulled in, switches the database off the same way, and everything
  it executes is ``gebra.*``.
* **The child reads one file outside the corpus** since TE-04: nothing, in fact, by default —
  ``tools.corpus_green`` would read ``docs/governance/FIDELITY-MATRIX.md`` to classify an R3.2
  shortfall, and the leg passes ``None`` so that it does not. Named here because the *module*
  is in the closure and a future leg that did hand it a matrix would be a read this list
  should already have anticipated. Read-only either way; no write path is added by TE-04.

Code calling the C-level ``_socket.socket`` directly would evade the wrapper — nothing in this
closure does, and the substrate-absence assertion keeps it that way. The ``subprocess`` and
raw-``_socket`` residuals are the ones VAL-13 accepted for the same pattern; the write-path
residual is new with TE-03 and the third-party-in-closure residual with TE-08, and both are
stated here so they are not absorbed into them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gebra.testing import load_corpus
from tests.conftest import FIXTURES_DIR

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A call to one of Python's execution primitives, as a *builtin* rather than as a method —
#: the lookbehind is what keeps ``re.compile(...)`` and ``ast.literal_eval(...)`` from reading
#: as ``compile(...)`` and ``eval(...)``.
_EXECUTION_PRIMITIVE = re.compile(r"(?<![\w.])(?:exec|eval|compile|__import__)\s*\(")

#: An import of a module whose whole purpose is to run something, load something by name, or
#: reconstruct an object from bytes. Matched as an import statement so that prose naming one
#: (every WA-07 docstring in this package names ``socket``) is not a hit.
_HAZARDOUS_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:importlib|imp|subprocess|runpy|ctypes|pickle|marshal|shelve"
    r"|socket|multiprocessing|asyncio)\b",
    re.MULTILINE,
)

#: The remaining ways to reach an interpreter or a process without an import statement.
_INDIRECT_EXECUTION = re.compile(
    r"(?:os\.(?:system|popen|exec|spawn|posix_spawn)|types\.FunctionType)"
)

#: An import of a substrate package, which the guarded child already refuses dynamically.
_SUBSTRATE_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:langgraph|langchain|langchain_core|langsmith)\b", re.MULTILINE
)

#: The guarded interpreter. Everything the load path can reach must run inside it.
_GUARD = '''
import json
import socket
import sys
from pathlib import Path

BLOCKED = (
    "langgraph", "langchain", "langchain_core", "langsmith",
    "openai", "anthropic", "httpx", "requests", "aiohttp", "urllib3",
)

#: Every tripwire records before it raises, so a caller that swallows still fails the run.
attempts = []


class SubstrateBlocker:
    """Refuse every substrate import, wherever on the load path it is attempted."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            attempts.append("import:" + fullname)
            print("WA07-TRIP", file=sys.stderr)
            raise ImportError("WA-07 tripwire: the load path imported " + repr(fullname))
        return None


class TripSocket(socket.socket):
    """Subclassed rather than replaced, so `class X(socket.socket)` stays definable."""

    def __new__(cls, *args, **kwargs):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("WA-07 tripwire: the load path created a socket")


def trip(label, message):
    def tripped(*args, **kwargs):
        attempts.append(label)
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("WA-07 tripwire: the load path " + message)

    return tripped


sys.meta_path.insert(0, SubstrateBlocker())
socket.socket = TripSocket
socket.getaddrinfo = trip("getaddrinfo", "resolved a name")
socket.create_connection = trip("create_connection", "opened a connection")

from gebra.testing import FixtureError, load_corpus
from tools.corpus_lint import check
from tools.corpus_reconcile import audit
from gebra.testing.harness import run_corpus
from tools.golden_harness import format_run

ROOT = Path("tests/fixtures/properties")
fixtures = load_corpus(ROOT)
composed = 0
non_composing = []
for fixture in fixtures:
    for ir in fixture.irs:
        assert ir.ir_version == "1.0"
    try:
        fixture.expected_report()
    except FixtureError:
        non_composing.append(fixture)
    else:
        composed += 1

report = check(ROOT, ROOT / "schema.yaml")
assert report.ok, report.violations

# The reconciliation pass reads the same corpus and rewrites blocks in memory; it joins the
# guarded run so that it joins the static scans below with it (TE-03).
reconciliation = audit(ROOT)

# The golden harness is the one path in this package that *calls* a registered validator, so
# it is the one that most needs proving it reaches no substrate, no socket and no interpreter
# (TE-02). The matrix cross-check is deliberately NOT run here: it would make this tripwire
# red whenever a governance document went stale, and a red tripwire is the last artifact
# anyone should be tempted to "fix". `tools.golden_harness` is imported and its renderer
# called so that the module still joins the closure the static scans below run over.
harness = run_corpus(ROOT)
rendered = format_run(harness)

# The corpus-green gate (TE-04). It is the one path here that runs `gebra.verify.verify()` —
# a whole thirteen-property run with its gate derivation — so it puts the aggregation, not
# only the individual validators, inside the guard. Its attribution pass also re-reads every
# non-composing `expected:` block and composes PR-1 projections out of them, which is a second
# pass over the corpus from a different direction. The matrix is deliberately NOT handed to
# it (`matrix_path=None`): that argument only decides whether an R3.2 shortfall reads as
# routed or as unrecorded, the gate is strictly stricter without it, and `parse_matrix`
# refuses a §3 with no rows — which is the *goal* state of the WA-04 loop. A governance
# document reaching its own end state must never turn a WA-07 tripwire red. What is asserted
# below is the shape of what the leg produced, never the verdict.
from tools.corpus_green import attribute, check as corpus_green

green = corpus_green(ROOT, ROOT / "schema.yaml", None)
attributed = sorted({attribute(fixture).cause for fixture in non_composing} - {None})
# The R3.4 clause is the one that runs `verify()`, and its own count is what says the
# aggregation reached thirteen properties rather than dying into a §2.4 tool-error report --
# which `verify()` produces by swallowing an exception, so a tripwire firing inside a
# validator would otherwise be invisible here. (`attempts` still catches it; this makes the
# leg say so directly.)
verified = int(green.clauses[3].findings[0].split(" answers ")[1].split(" ")[0])

# The generation path (TE-08): the strategies build IR models out of generated primitives, and
# P-01 runs over every draw. `deadline=None` because a cold guarded interpreter is not the place
# to measure per-example latency, and `database=None` so the child writes nothing; no health
# check is suppressed. The example count is small on purpose — the *scale* claim is
# `tests/testing/test_strategies.py`'s, and what this leg adds is the interpreter.
from hypothesis import given, settings
from gebra.testing.strategies import workflow_irs
from gebra.verify.properties.graph_well_formed import check_graph_well_formed

verdicts = []


@settings(max_examples=25, deadline=None, database=None)
@given(workflow_irs())
def generate(ir):
    verdicts.append(check_graph_well_formed(ir).result)


generate()

# The mutation path (TE-10): the operators rewrite a generated workflow into one that breaks a
# contract or advisory property at one point, and the three validators that own those properties
# run over BOTH halves of every mutation — so the adversarial shapes (a dangling compensation
# hook, an unwritten read, a determinism claim on a remote-provider node) reach a validator
# inside the guard. Each family is driven separately rather than through the combined strategy,
# so the target set below is a deterministic assertion instead of a probabilistic one.
from gebra.testing.mutations import (
    dataflow_mutations,
    determinism_mutations,
    effect_safety_mutations,
)
from gebra.verify.properties.dataflow_completeness import check_dataflow_completeness
from gebra.verify.properties.determinism_replay import check_determinism_replay
from gebra.verify.properties.effect_safety import check_effect_safety

CHECKS = {
    "dataflow-completeness": check_dataflow_completeness,
    "effect-safety": check_effect_safety,
    "determinism-replay": check_determinism_replay,
}
mutated = []


def drive(strategy):
    # `derandomize=True`, unlike the generation leg above: `mutated_as_predicted` is a
    # *correctness* assertion living inside a hermeticity tripwire, and a rare draw that
    # disagreed would turn this file red for a reason that has nothing to do with WA-07. The
    # predictions are separately quantified at a thousand examples in
    # tests/testing/test_metaproperties_contract.py; what this leg is for is the interpreter.
    @settings(max_examples=25, deadline=None, database=None, derandomize=True)
    @given(strategy)
    def run(mutation):
        check = CHECKS[mutation.target]
        expected = "fail" if mutation.breaking else "pass"
        mutated.append((
            mutation.target,
            check(mutation.origin).result == "pass" and check(mutation.ir).result == expected,
        ))

    run()


for family in (dataflow_mutations(), effect_safety_mutations(), determinism_mutations()):
    drive(family)

# The structural path (TE-09): the same shape one property down. What it adds over the leg above
# is the two validators that read the *graph* rather than a contract, over input built to break
# it — a document with a reference resolving to nothing, and a document carrying a cycle whose
# only declared termination witness has just been removed. Both are places a validator could
# plausibly try to resolve something: P-01 spells an unresolved reference back into a report, and
# P-02 hands every router's declared `condition` to the §3 recognizer, which is a regular
# expression over declared text and must stay one. The census and the dominator pass run here too.
from gebra.testing.mutations import termination_mutations, well_formedness_mutations
from gebra.verify.properties.termination_witness import check_termination_witness

STRUCTURAL = {
    "graph-well-formed": check_graph_well_formed,
    "termination-witness": check_termination_witness,
}
structural = []


def drive_structural(strategy):
    # `derandomize=True` for the reason `drive` above carries it: `structural_as_predicted` is a
    # *correctness* assertion living inside a hermeticity tripwire, and a rare draw that
    # disagreed would turn this file red for a reason that has nothing to do with WA-07. The
    # predictions are separately quantified at a thousand examples in
    # tests/testing/test_metaproperties_structural.py; what this leg is for is the interpreter.
    @settings(max_examples=25, deadline=None, database=None, derandomize=True)
    @given(strategy)
    def run(mutation):
        check = STRUCTURAL[mutation.target]
        expected = "fail" if mutation.breaking else "pass"
        structural.append((
            mutation.target,
            check(mutation.origin).result == "pass" and check(mutation.ir).result == expected,
        ))

    run()


for family in (well_formedness_mutations(), termination_mutations()):
    drive_structural(family)


def emit():
    print(json.dumps({
        "loaded": len(fixtures),
        "composed": composed,
        "reconciliation_outstanding": len(reconciliation.outstanding),
        "reconciliation_verified": len(reconciliation.verifications)
        - len(reconciliation.failed_verifications),
        "harness_obligations": len(harness.outcomes),
        "harness_matched": harness.counts["matched"],
        "harness_rendered": len(rendered.splitlines()),
        "green_clauses": [clause.id for clause in green.clauses],
        "green_findings": sum(len(clause.findings) for clause in green.clauses),
        "green_attributed": attributed,
        "green_verified_properties": verified,
        "green_r34_violations": len(green.clauses[3].violations),
        "generated": len(verdicts),
        "generated_verdicts": sorted(set(verdicts)),
        "mutated": len(mutated),
        "mutated_targets": sorted({target for target, _ in mutated}),
        "mutated_as_predicted": all(agreed for _, agreed in mutated),
        "structural": len(structural),
        "structural_targets": sorted({target for target, _ in structural}),
        "structural_as_predicted": all(agreed for _, agreed in structural),
        "leaked": sorted(n for n in sys.modules if n.split(".")[0] in BLOCKED),
        "attempts": list(attempts),
        "sources": sorted(
            module.__file__
            for name, module in list(sys.modules.items())
            if name.split(".")[0] in ("gebra", "tools") and getattr(module, "__file__", None)
        ),
    }))


emit()
'''


def _run_guarded(control: str = "") -> subprocess.CompletedProcess[str]:
    """Run the load path in a fresh interpreter with the substrate and sockets tripwired."""
    return subprocess.run(
        [sys.executable, "-c", _GUARD + control],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _payloads(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    """Every JSON object the guarded child emitted, in order."""
    payloads = []
    for line in result.stdout.splitlines():
        try:
            payloads.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return payloads


@pytest.fixture(scope="module")
def guarded() -> dict[str, Any]:
    """One clean guarded run, shared by the assertions that read its report."""
    result = _run_guarded()
    assert result.returncode == 0, result.stderr
    payloads = _payloads(result)
    assert payloads, result.stdout
    return payloads[0]


# ── The claim ────────────────────────────────────────────────────────────────────────────


def test_the_load_path_imports_no_substrate_and_opens_no_socket(
    guarded: dict[str, Any],
) -> None:
    """Load sixty fixtures, lint them, audit the reconciliation, run the harness, generate,
    mutate — all guarded.

    The substrate import, the socket and the name resolution each raise inside this child, so
    a green run is the claim: none of the eight legs reaches any of them. Five of them
    **execute** rather than merely import. The harness runs every registered validator over
    every fixture — all five wedge validators are registered (``check_determinism_replay``,
    VAL-04; ``check_graph_well_formed``, VAL-05; ``check_dataflow_completeness``, VAL-09;
    ``check_effect_safety``, VAL-10; ``check_termination_witness``, VAL-07), so what a green
    run says precisely is that those five read serialized IR and reach nothing else — and
    the matched count is asserted rather than assumed, so a validator that stopped
    registering would drop it and fail here. The generation leg (TE-08) runs hypothesis and
    P-01 over IR that no fixture authored, and its verdict set is asserted rather than only its
    count, so a generator that silently produced nothing, or ill-formed IR, fails here too.
    The mutation leg (TE-10) runs three validators over *deliberately broken* IR — the widest
    input surface in the repository — and asserts that each one reached the verdict its operator
    predicted, so a leg that produced nothing, or documents no validator could read, fails here
    rather than passing as "no violation observed". The structural leg (TE-09) does the same for
    P-01 and P-02 over broken *topology*: an unresolvable reference and an unwitnessed cycle,
    which is where the §3 guard recognizer and the abort-capped census run under the guard, and
    the only leg whose input a validator could not analyse at all without first declining to
    resolve something. The corpus-green leg (TE-04) is the only one
    that runs ``gebra.verify.verify()`` — the whole thirteen-property aggregation and its gate
    derivation — and it re-reads every non-composing ``expected:`` block to attribute it, so
    both the aggregation and the attribution pass are inside the guard; its four clause ids and
    the set of causes it derived are asserted, so a leg that silently attributed nothing fails
    here rather than reporting a shorter list.
    """
    assert guarded["loaded"] == 60
    assert guarded["composed"] == 33
    assert guarded["reconciliation_outstanding"] == 0
    assert guarded["reconciliation_verified"] == 14
    assert guarded["harness_obligations"] == 78
    assert guarded["harness_matched"] == 44
    assert guarded["harness_rendered"] == 78
    assert guarded["generated"] == 25
    assert guarded["generated_verdicts"] == ["pass"]
    assert guarded["mutated"] == 75
    assert guarded["mutated_targets"] == [
        "dataflow-completeness",
        "determinism-replay",
        "effect-safety",
    ]
    assert guarded["mutated_as_predicted"] is True
    assert guarded["structural"] == 50
    assert guarded["structural_targets"] == ["graph-well-formed", "termination-witness"]
    assert guarded["structural_as_predicted"] is True
    assert guarded["green_clauses"] == ["R3.1", "R3.2", "R3.3", "R3.4"]
    assert guarded["green_findings"] == 11
    assert guarded["green_attributed"] == [
        "held-back-condition-id",
        "non-wedge-component",
        "non-wedge-owner",
        "run-level-wrapper",
    ]
    assert guarded["green_verified_properties"] == 13
    assert guarded["green_r34_violations"] == 0
    assert guarded["leaked"] == []
    assert guarded["attempts"] == []


def test_the_guarded_run_covers_the_whole_load_path(guarded: dict[str, Any]) -> None:
    """The reported closure is the load path, not a hand-kept subset of it.

    Every registered validator's module is named here rather than left to the matched count:
    that is what says the guarded run really *executed* it, instead of the count happening to
    add up for some other reason.
    """
    sources = {Path(path).name for path in guarded["sources"]}
    assert {
        "fixtures.py",
        "harness.py",
        "strategies.py",
        "mutations.py",
        "corpus_lint.py",
        "corpus_reconcile.py",
        "golden_harness.py",
        "corpus_green.py",
        "determinism_replay.py",
        "graph_well_formed.py",
        "dataflow_completeness.py",
        "effect_safety.py",
        "termination_witness.py",
        "serialization.py",
        "report.py",
    } <= sources
    # 33 on the tree this floor was last measured against (TE-09), so 30 leaves ~9% headroom.
    # It was `>= 18` until then — a number that had moved +1 per card rather than being derived,
    # and that therefore tolerated **45%** of the closure vanishing from the report. That is not
    # a cosmetic slack: the two static scans below iterate exactly this list, so a truncated
    # `sources` makes both of them silently vacuous. The headroom is deliberate in the other
    # direction too — a floor pinned at the exact count would turn this tripwire red on a
    # legitimate lazy-import refactor, which is a red tripwire for a non-WA-07 reason.
    assert len(guarded["sources"]) >= 30


# ── Both halves of the tripwire are armed ────────────────────────────────────────────────


def test_the_substrate_blocker_is_armed() -> None:
    """The negative control: the same interpreter, plus one substrate import, must fail."""
    result = _run_guarded("\nimport langgraph\n")
    assert result.returncode != 0
    assert "WA-07 tripwire" in result.stderr
    assert "langgraph" in result.stderr


def test_a_swallowed_substrate_import_still_fails_the_run() -> None:
    """Recording before raising is what makes a ``except ImportError: pass`` path visible."""
    result = _run_guarded(
        "\ntry:\n    import langchain_core\nexcept ImportError:\n    pass\nemit()\n"
    )
    assert result.returncode == 0, result.stderr
    assert _payloads(result)[-1]["attempts"] == ["import:langchain_core"]


def test_the_socket_tripwire_is_armed() -> None:
    result = _run_guarded("\nsocket.socket()\n")
    assert result.returncode != 0
    assert "created a socket" in result.stderr


def test_a_swallowed_socket_attempt_still_fails_the_run() -> None:
    result = _run_guarded("\ntry:\n    socket.socket()\nexcept AssertionError:\n    pass\nemit()\n")
    assert result.returncode == 0, result.stderr
    assert _payloads(result)[-1]["attempts"] == ["socket"]


def test_the_dns_tripwire_is_armed() -> None:
    result = _run_guarded("\nsocket.getaddrinfo('example.invalid', 80)\n")
    assert result.returncode != 0
    assert "resolved a name" in result.stderr


def test_a_socket_subclass_stays_definable() -> None:
    """Instantiation trips; defining a subclass — as ``ssl`` does — must not."""
    result = _run_guarded("\nclass Sub(socket.socket):\n    pass\nemit()\n")
    assert result.returncode == 0, result.stderr
    assert _payloads(result)[-1]["attempts"] == []


# ── Static scans, over the closure the guarded run reported ──────────────────────────────


def test_the_load_path_holds_no_execution_primitive(guarded: dict[str, Any]) -> None:
    """``source_snippet`` cannot be executed by code that reaches no interpreter at all."""
    for path in guarded["sources"]:
        source = Path(path)
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in (_EXECUTION_PRIMITIVE, _HAZARDOUS_IMPORT, _INDIRECT_EXECUTION):
                found = pattern.search(line)
                if found is not None:
                    pytest.fail(
                        f"{source.relative_to(REPO_ROOT)}:{number} reaches {found.group()!r}"
                        " — the fixture load path never executes document content (WA-07)"
                    )


def test_the_load_path_names_no_substrate_module(guarded: dict[str, Any]) -> None:
    """Belt to the guarded run's braces, over the same closure it reported."""
    for path in guarded["sources"]:
        source = Path(path)
        assert _SUBSTRATE_IMPORT.search(source.read_text(encoding="utf-8")) is None, source


def test_every_carried_source_snippet_is_an_inert_string() -> None:
    """The corpus's illustrative Python is data on this side of the boundary, and only data."""
    snippets = [
        fixture for fixture in load_corpus(FIXTURES_DIR) if fixture.source_snippet is not None
    ]
    assert snippets, "no fixture carries a source_snippet — this test would prove nothing"
    for fixture in snippets:
        assert isinstance(fixture.source_snippet, str), fixture.fixture_id
