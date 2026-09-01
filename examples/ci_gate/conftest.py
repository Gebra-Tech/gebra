"""Declare which workflow the gebra fixtures are about.

``gebra_workflow`` is the one fixture a suite overrides. Everything else follows from it:
``gebra_graph`` is this workflow's extracted IR, and ``gebra_verification`` is the whole
verification run over that IR. Nothing here runs the workflow — the builder is handed to
gebra, which imports and inspects it.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.sample_workflows.travel_booking import build_travel_booking_agent


@pytest.fixture
def gebra_workflow() -> Any:
    """The workflow under verification — in your repository, your own builder."""
    return build_travel_booking_agent()
