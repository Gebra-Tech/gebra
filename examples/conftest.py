"""The never-invokes tripwire over the runnable examples (WA-07; cards DOC-13, TE-05).

Repository-only machinery, deliberately one level above ``ci_gate/``: the files in that
directory are reproduced verbatim in ``docs/guides/pytest-plugin-and-ci-gating.md`` and held
byte-equal to the page, so tripwire plumbing there would leak into a snippet adopters copy.

What it holds. Every example here marks the shared travel-booking fixture family, whose node
bodies record into ``travel_booking.TRIPPED`` and then raise (``travel_booking_defects``
re-exports that same list object rather than keeping a second one). Asserting the ledger empty
on entry to and exit from every test is what keeps the example suite's greenness a statement
about gebra reading a definition rather than about a run that happened to survive. It matters
most on the ``report-only`` rung of ``.github/workflows/gebra-gate-example.yml``, whose asserted
verdict is ``exit 1`` / ``failures`` — the outcome a fired sentinel would also produce, so
without this fixture that step alone could not tell the seeded finding from an invocation.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.sample_workflows import travel_booking


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """No node body ran — asserted before and after every example test (the TE-05 idiom)."""
    assert travel_booking.TRIPPED == []
    yield
    assert travel_booking.TRIPPED == []
