"""pytest plugin + golden-fixture harness — brief D-10.

What has landed so far is the **fixture loader**: the hermetic path from a vendored property
fixture on disk to the two model surfaces it is a triple over — ``ir_version`` 1.0
:class:`~gebra.ir.WorkflowIR` for the IR blocks, and the PROPERTY-CATALOG-SPEC §0.3
:class:`~gebra.verify.PropertyReport` for the ``expected:`` block::

    from gebra.testing import load_corpus

    for fixture in load_corpus("tests/fixtures/properties"):
        fixture.ir                  # a WorkflowIR (or ir_before/ir_after for a P-12 pair)
        fixture.expected_report()   # the same class a validator returns (A6 PC-6)

Loading is *shape* only. Whether the corpus satisfies the schema's envelope rules, the
counts table, the naming convention and the one-IR-shape rule is the corpus lint's question
(``tools/corpus_lint.py``, run as its own CI job).

Whether a validator agrees with an ``expected:`` block is the **golden harness**'s, and that
has landed too: :mod:`gebra.testing.harness` turns each fixture into one *obligation* per
property it exercises and compares each against the validator that owns it as
PROPERTY-CATALOG-SPEC §0.3 model equality — set-comparison on the fields the specs mark
order-free, never string or raw-dict equality::

    from gebra.testing import run_corpus

    run = run_corpus("tests/fixtures/properties")
    run.counts                  # matched / pending-validator / deferred-to-phase-1 / …
    run.deviations              # every disagreement, each a fidelity-matrix entry

A property outside the Phase-0 wedge is a named, counted, structured skip citing SOW §8 —
never a silent pass — exactly as :func:`gebra.verify.not_implemented` answers at the API
level.

Where the corpus stops, **generation** starts: :mod:`gebra.testing.strategies` produces
well-formed ``ir_version`` 1.0 workflows for hypothesis, so a property can be quantified over
shapes no fixture authored, and :mod:`gebra.testing.mutations` rewrites one of those into a
workflow that breaks exactly one of the five wedge properties at exactly one point — an
unwritten read, an unprotected effect, an incoherent determinism claim, an unresolvable
reference, a cycle whose termination witness has just been removed — carrying the verdict the
validator that owns it must reach, so a metaproperty asserts against a prediction rather than
against whatever came out::

    from gebra.testing.strategies import workflow_irs   # needs hypothesis installed
    from gebra.testing.mutations import mutations       # likewise

Those two are the modules here that are *not* re-exported below, because they are the ones that
need ``hypothesis`` — a development dependency, so importing this package must not pull it in.

Nothing here imports langgraph or langchain, opens a socket, or executes a workflow node or
any document content — ``source_snippet`` is carried as an inert string and never compiled
(WA-07). The one thing that *is* executed is a registered validator, which
:func:`run_corpus` calls: a hermetic in-repo function over serialized IR, and
``tests/testing/test_hermeticity.py`` runs the whole of it — loader, lint, harness, the
strategies and the mutation operators — in an interpreter where a substrate import, a socket
and a name resolution each raise.
"""

from gebra.testing.fixtures import (
    FIXTURE_SUFFIX,
    IR_KEYS,
    PROPERTY_SLUGS,
    SCHEMA_FILENAME,
    FixtureError,
    FixtureErrorReason,
    Polarity,
    PropertyFixture,
    fixture_from_document,
    iter_fixture_paths,
    load_corpus,
    load_fixture,
    load_fixture_document,
    yaml_loader,
)
from gebra.testing.harness import (
    PROJECTION_RULES,
    STATUS_ORDER,
    CorpusRun,
    Obligation,
    ObligationKind,
    Outcome,
    OutcomeStatus,
    ProjectionRule,
    expected_for,
    plan_corpus,
    plan_fixture,
    projection_rule,
    run_corpus,
    run_fixture,
    run_obligation,
)

__all__ = [
    "FIXTURE_SUFFIX",
    "IR_KEYS",
    "PROJECTION_RULES",
    "PROPERTY_SLUGS",
    "SCHEMA_FILENAME",
    "STATUS_ORDER",
    "CorpusRun",
    "FixtureError",
    "FixtureErrorReason",
    "Obligation",
    "ObligationKind",
    "Outcome",
    "OutcomeStatus",
    "Polarity",
    "ProjectionRule",
    "PropertyFixture",
    "expected_for",
    "fixture_from_document",
    "iter_fixture_paths",
    "load_corpus",
    "load_fixture",
    "load_fixture_document",
    "plan_corpus",
    "plan_fixture",
    "projection_rule",
    "run_corpus",
    "run_fixture",
    "run_obligation",
    "yaml_loader",
]
