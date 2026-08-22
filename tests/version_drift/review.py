"""Review-proposal machinery for the §3 rows that block *and* route a governance review.

Two VERSION-COMPAT §3 rows attach a governance consequence to specific failure branches,
beyond the blocking itself:

* **Row 4** (`test_drift_get_graph_drawable_fidelity`): both failure branches block the
  cell and open a version-gap issue; when the drawable payload diverged **while the
  builder-derived core IR is still golden**, the row additionally says *"propose demoting
  the `get_graph` cross-check via §5 R-06 governance — an assertion downgrade, never a
  repo-doc-only edit"*.
* **Row 8** (`test_drift_context_schema_surface`): a ``config_schema=`` construction that
  raises ``TypeError`` is the documented 2.0 removal observed — *"2.0 ceiling reached →
  block cell + freeze range + open major-version review via §5 R-06 governance"*.

A blocked cell cannot file a vault review itself; what it can do is put the complete,
correctly-routed proposal in front of the humans and the automation. So a firing branch
records a :class:`ReviewProposal` — a templated document naming the trigger, the observed
facts, and the §5 R-06 routing — **before** its blocking assertion fails, and the proposal
is emitted through every channel a CI run exposes:

* immediately on record: a file drop (``<kind>.md``) into ``$GEBRA_DRIFT_REVIEW_DIR`` when
  set, and the full body appended to ``$GITHUB_STEP_SUMMARY`` when set (the run-summary
  pane, visible without opening a log);
* at terminal-summary time (the package ``conftest.py``): a titled section with the body,
  one stable machine-readable :data:`REVIEW_MARKER` line per proposal — the GOV-07
  issue-automation seam, same contract as ``DRIFT-SOFT-DIVERGENCE`` — and a ``::warning``
  workflow command under GitHub Actions so the proposal reaches the annotations pane
  (§3: warnings never live only in logs; the *blocking* is the red cell itself).

Nothing here talks to GitHub, opens issues, or edits any document: opening the version-gap
issue is GOV-07's machinery, and the proposed ruling itself is R-06 vault governance's to
make (WA-03 — the suite never improvises semantics, it routes).

:func:`classify_config_schema_probe` is row 8's outcome classifier, substrate-free on
purpose: it runs whatever zero-argument probe it is handed under a recording warnings
filter, so the dry-run tests can drive every branch with stub probes and the real test
hands it the live legacy factory.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

from tests import substrate

#: The stable, machine-readable prefix GOV-07's issue automation greps for — one line per
#: proposal: ``DRIFT-REVIEW-PROPOSAL kind=<kind> test=<test> detail=<free text to EOL>``.
#: ``kind`` and ``test`` are single tokens; ``detail`` runs to the end of the line.
REVIEW_MARKER: Final = "DRIFT-REVIEW-PROPOSAL"

#: The environment variable naming a directory to drop ``<kind>.md`` proposal files into.
REVIEW_DIR_VARIABLE: Final = "GEBRA_DRIFT_REVIEW_DIR"


@dataclass(frozen=True)
class ReviewProposal:
    """One templated review proposal: what fired, what was observed, where it routes."""

    kind: str
    """Single-token proposal kind: ``get-graph-demotion`` or ``major-version-review``."""
    test: str
    """The §3 test whose failure branch recorded this."""
    detail: str
    """One factual line — the observation that distinguishes this firing."""
    body: str
    """The full markdown proposal document."""

    def message(self) -> str:
        """The one-line machine-readable form — the GOV-07 seam, stable by contract."""
        detail = " ".join(self.detail.split())
        return f"{REVIEW_MARKER} kind={self.kind} test={self.test} detail={detail}"


#: Every proposal this run recorded, in recording order. The package ``conftest.py``
#: reports them at terminal-summary time; tests never read this.
PROPOSALS: list[ReviewProposal] = []


def _installed_pair() -> str:
    """The substrate pair under test, for the proposal bodies."""
    langgraph = ".".join(map(str, substrate.LANGGRAPH_VERSION))
    core = ".".join(map(str, substrate.LANGCHAIN_CORE_VERSION))
    return f"langgraph {langgraph} / langchain-core {core}"


def propose(proposal: ReviewProposal) -> None:
    """Record a proposal and emit its immediate artifacts.

    Called **before** the branch's blocking assertion fails, so the artifact exists even if
    the run stops at that failure. The terminal-summary emission is the conftest's.
    """
    PROPOSALS.append(proposal)
    directory = os.environ.get(REVIEW_DIR_VARIABLE)
    if directory:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{proposal.kind}.md").write_text(
            proposal.body + "\n" + proposal.message() + "\n", encoding="utf-8"
        )
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as stream:
            stream.write(proposal.body + "\n\n" + "`" + proposal.message() + "`\n\n")


def get_graph_demotion_proposal(
    committed: dict[str, Any], observed: dict[str, Any]
) -> ReviewProposal:
    """Row 4's branch proposal: the drawing diverged while the builder path held."""
    detail = (
        f"drawable payload diverged (committed {committed.get('node_count')} nodes/"
        f"{committed.get('edge_count')} edges, observed {observed.get('node_count')} nodes/"
        f"{observed.get('edge_count')} edges) while the builder-derived core IR is still "
        "golden"
    )
    body = f"""# Drift review proposal — demote the `get_graph` cross-check

- **Trigger**: `test_drift_get_graph_drawable_fidelity` (VERSION-COMPAT §3 row 4) on
  {_installed_pair()}: the drawable payload diverged from its committed golden while the
  builder-derived core IR still matches its golden byte-for-byte.
- **What §3 row 4 rules for this branch**: the cell is blocked and a version-gap issue is
  opened (both branches do that); because the builder path is still golden, this run
  additionally proposes demoting the `get_graph` drawable cross-check.
- **Routing**: an assertion downgrade routes through VERSION-COMPAT §5 R-06 governance —
  never a repo-doc-only edit. The suite keeps blocking this cell until an R-06 ruling
  lands and the living document records it per §5; the suite never improvises the
  downgrade itself (WA-03).
- **Observed**: {detail}.
- **Context that survives this firing**: builder attributes remain the primary extraction
  source and `get_graph()` a cross-check only (§2; A1 judgment 1) — the divergence is
  between the drawing and the builder truth, not inside the extraction contract.
"""
    return ReviewProposal(
        kind="get-graph-demotion",
        test="test_drift_get_graph_drawable_fidelity",
        detail=detail,
        body=body,
    )


def major_version_review_proposal(error: str) -> ReviewProposal:
    """Row 8's removal proposal: the documented 2.0 removal was observed live."""
    detail = f"config_schema= raised instead of deprecation-warning-and-working: {error}"
    body = f"""# Drift review proposal — 2.0 ceiling reached: open the major-version review

- **Trigger**: `test_drift_context_schema_surface` (VERSION-COMPAT §3 row 8) on
  {_installed_pair()}: constructing `StateGraph(..., config_schema=...)` raised `TypeError`
  instead of emitting the deprecation warning — the removal documented for 2.0 has been
  observed on this substrate.
- **What §3 row 8 rules**: block this cell, freeze the supported range — cap the tested
  ceiling at the last green pair (§4 red path) — and open the major-version review via §5
  R-06 governance.
- **Routing**: a range ruling goes through R-06 vault governance first, never a repo-only
  edit (§5 update discipline). The §4 2.0-watch applies alongside: an immediate `--pre`
  cell run and a supported-range review.
- **Observed**: {detail}.
"""
    return ReviewProposal(
        kind="major-version-review",
        test="test_drift_context_schema_surface",
        detail=detail,
        body=body,
    )


class ConfigSchemaOutcome(Enum):
    """What the row-8 legacy construction did on this substrate."""

    DEPRECATED_WORKS = "deprecated-works"
    """Constructed, and a ``DeprecationWarning`` (subclass) was emitted — the green row."""
    REMOVED = "removed"
    """``TypeError`` — the kwarg is gone: the 2.0 ceiling, row 8's proposal branch."""
    SILENT = "silent"
    """Constructed with no deprecation warning — drift (the marker vanished), no proposal."""


@dataclass(frozen=True)
class ConfigSchemaProbe:
    """One classified run of the legacy construction probe."""

    outcome: ConfigSchemaOutcome
    built: Any | None
    """The constructed builder on the two non-raising outcomes, else ``None``."""
    warning_class_names: frozenset[str]
    """The warning classes the construction emitted — test 8's soft-inventory surface."""
    error: str | None
    """The ``TypeError`` text on :attr:`ConfigSchemaOutcome.REMOVED`, else ``None``."""


def classify_config_schema_probe(probe: Callable[[], Any]) -> ConfigSchemaProbe:
    """Run the legacy-construction probe under a recording filter and classify it.

    Only ``TypeError`` reads as the removal (an unexpected-keyword refusal is how a removed
    constructor kwarg presents); any other exception propagates — an unexpected failure
    shape should fail the test loudly as itself, not be folded into a classification.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            built = probe()
        except TypeError as error:
            names = frozenset(record.category.__name__ for record in caught)
            return ConfigSchemaProbe(
                outcome=ConfigSchemaOutcome.REMOVED,
                built=None,
                warning_class_names=names,
                error=f"TypeError: {error}",
            )
    names = frozenset(record.category.__name__ for record in caught)
    deprecated = any(issubclass(record.category, DeprecationWarning) for record in caught)
    return ConfigSchemaProbe(
        outcome=ConfigSchemaOutcome.DEPRECATED_WORKS if deprecated else ConfigSchemaOutcome.SILENT,
        built=built,
        warning_class_names=names,
        error=None,
    )
