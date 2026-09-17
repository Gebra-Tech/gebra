"""The never-invokes tripwire over the runnable examples (WA-07; cards DOC-13, TE-05, REL-06).

Repository-only machinery, deliberately one level above the example suites: the files in
``ci_gate/`` and in every ``scenarios/<slug>/`` are reproduced verbatim on a documentation
page and held byte-equal to it, so tripwire plumbing there would leak into a snippet
adopters copy.

What it holds. Every example here reads a guarded definition: ``ci_gate/`` marks the shared
travel-booking fixture family, whose node bodies record into ``travel_booking.TRIPPED`` and
then raise (``travel_booking_defects`` re-exports that same list object rather than keeping a
second one), and each scenario under ``scenarios/`` keeps a ``TRIPPED`` of its own in its
``workflow.py``. Asserting every ledger empty on entry to and exit from every test is what
keeps the example suites' greenness a statement about gebra reading a definition rather than
about a run that happened to survive. It matters most on the ``report-only`` rung of
``.github/workflows/gebra-gate-example.yml``, whose asserted verdict is ``exit 1`` /
``failures`` — the outcome a fired sentinel would also produce, so without this fixture that
step alone could not tell the seeded finding from an invocation.

The scenario ledgers are **discovered, not listed**: every ``scenarios/*/workflow.py`` is
imported and asked for its ``TRIPPED``, and a scenario that keeps none is refused at import
rather than read as clean — "nothing was recorded" must not give the same answer as "nothing
ran", which is the documentation harness's own fail-closed rule. A fourth scenario is swept
without an edit here.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from tests.sample_workflows import travel_booking

#: Where the scenarios live — one directory per scenario, each with a ``workflow.py``.
SCENARIOS: Final = Path(__file__).resolve().parent / "scenarios"


def _scenario_ledgers() -> dict[str, list[str]]:
    """Every ledger this conftest sweeps, by name — the family's, then one per scenario."""
    ledgers: dict[str, list[str]] = {"travel_booking": travel_booking.TRIPPED}
    for workflow in sorted(SCENARIOS.glob("*/workflow.py")):
        slug = workflow.parent.name
        module = importlib.import_module(f"examples.scenarios.{slug}.workflow")
        ledger = getattr(module, "TRIPPED", None)
        if not isinstance(ledger, list):
            raise TypeError(
                f"examples/scenarios/{slug}/workflow.py keeps no TRIPPED ledger, so a body of "
                "it that ran inside a try block would leave no trace. Give the module a "
                "module-level `TRIPPED: list[str]` that every body records into before raising."
            )
        ledgers[slug] = ledger
    return ledgers


#: The ledgers, discovered once at collection. Each value is the module's own list object,
#: never a copy — a copy would read empty forever.
LEDGERS: Final[dict[str, list[str]]] = _scenario_ledgers()


def _fired() -> dict[str, list[str]]:
    """The non-empty ledgers, by name — ``{}`` is the only acceptable answer."""
    return {name: list(ledger) for name, ledger in LEDGERS.items() if ledger}


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """No node body ran — asserted before and after every example test (the TE-05 idiom)."""
    assert _fired() == {}
    yield
    assert _fired() == {}
