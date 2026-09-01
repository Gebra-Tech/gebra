"""A variant that fails its gate on purpose — what the report-only rung has to report.

This module marks the travel-booking agent with one edit: the billable ``book_flight`` node
has lost its ``@gebra.idempotent`` protection while staying inside the booking retry region.
P-06 reports an ERROR there, so the ``effect-safety`` item fails and the run exits 1. Under
``mode: report-only`` the CI step is green anyway and the finding lands in the step summary;
under ``mode: gate`` the same run is red. It is kept out of ``testpaths`` so a bare ``pytest``
over this repository never collects it.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.sample_workflows.travel_booking_defects import build_defect_2_unprotected_retry


@pytest.mark.gebra(name="unprotected_retry")
def test_gebra() -> Any:
    """Return the defective variant; `effect-safety` is the item that fails."""
    return build_defect_2_unprotected_retry()
