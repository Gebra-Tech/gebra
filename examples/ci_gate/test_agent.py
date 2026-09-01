"""The whole of a first gebra gate: one marked function, plus assertions of your own.

The marked function is the gate — the plugin calls it, extracts what it returns and reports
one test item per checked property. The two tests under it are ordinary pytest, written
against the fixtures the plugin ships.
"""

from __future__ import annotations

from typing import Any

import pytest

from gebra.ir import WorkflowIR
from gebra.pytest_plugin import TargetVerification
from tests.sample_workflows.travel_booking import build_travel_booking_agent


@pytest.mark.gebra(name="travel_agent")
def test_gebra() -> Any:
    """Return the workflow to verify; one item per property is generated from it."""
    return build_travel_booking_agent()


def test_the_compensating_path_is_still_wired(gebra_graph: WorkflowIR) -> None:
    """`gebra_graph` is the extracted IR — assert against it like any other value."""
    assert "release_hotel_hold" in {node.id for node in gebra_graph.nodes}


def test_no_property_reported_a_blocking_finding(gebra_verification: TargetVerification) -> None:
    """`gebra_verification` is the whole run: all thirteen outcomes and the derived gate."""
    gate = gebra_verification.report.gate
    assert (gate.counts.fatal, gate.counts.error) == (0, 0)
