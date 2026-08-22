"""Version-drift suite wiring: the armed-fixture ledger and the end-of-run emissions.

Three responsibilities, all package-scoped:

* **WA-07 ledger.** The autouse fixture asserts, after every test in this package, that no
  armed fixture body was reached — extraction, drawing, schema rendering, and every surface
  read must leave :data:`tests.version_drift.workflows.TRIPPED` empty.

* **Soft-divergence emission.** VERSION-COMPAT §3: a soft-only divergence "keeps the cell
  green, emits a CI annotation ... Warnings never live only in logs." The tests collect
  divergences through :func:`tests.version_drift.inventory.soft_exact_set`; this hook
  emits them once, at terminal-summary time — under GitHub Actions as ``::warning``
  workflow commands, which the runner lifts into the run's annotations pane (visible
  without opening the log), and everywhere as a titled terminal section. The
  ``DRIFT-SOFT-DIVERGENCE`` line is the stable machine-readable seam GOV-07's version-gap
  issue automation consumes; opening the issue is that card's machinery, not this hook's.

* **Review-proposal emission.** The §3 row-4/row-8 failure branches record templated
  governance proposals through :func:`tests.version_drift.review.propose` (which also drops
  the immediate file artifacts) *before* their blocking assertion fails; this hook emits
  each proposal's full body, its stable ``DRIFT-REVIEW-PROPOSAL`` line — the same GOV-07
  seam contract — and a ``::warning`` workflow command under Actions. The blocking itself
  is the red cell; the annotation is how the proposal reaches the run UI beside it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from tests.version_drift import inventory, review, workflows


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """Every test in this package asserts the armed fixtures were read, never run."""
    del workflows.TRIPPED[:]
    yield
    assert workflows.TRIPPED == []


def pytest_terminal_summary(terminalreporter: object) -> None:
    """Emit collected soft divergences and review proposals — annotation-grade."""
    writer = terminalreporter
    section = getattr(writer, "section", None)
    write_line = getattr(writer, "write_line", print)
    under_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    if inventory.DIVERGENCES:
        if callable(section):
            section("version-drift soft divergences (cells stay green; VERSION-COMPAT §3)")
        for divergence in inventory.DIVERGENCES:
            write_line(divergence.sentence())
            write_line(divergence.message())
            if under_actions:
                write_line(f"::warning title=version-drift soft divergence::{divergence.message()}")
    if review.PROPOSALS:
        if callable(section):
            section("version-drift review proposals (cells blocked; VERSION-COMPAT §3/§5)")
        for proposal in review.PROPOSALS:
            for line in proposal.body.splitlines():
                write_line(line)
            write_line(proposal.message())
            if under_actions:
                write_line(f"::warning title=version-drift review proposal::{proposal.message()}")
