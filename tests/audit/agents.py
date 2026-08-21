"""The travel-booking agent, and the same agent after one edit — SD-07's "the agent changed".

Acceptance box 2 is "freshness check fails CI when the agent changes without re-snapshot", so
the tests need *two* extractions of a real agent that differ. The first is TE-05's shared
travel-booking fixture, unchanged. The second is that fixture with one node added and wired in
— built here rather than in ``tests/sample_workflows/travel_booking.py``, which is a done
card's artifact and whose ``narrow_input_schema`` counterfactual is documented in terms as "not
a version of this agent" and explicitly not to be snapshotted.

What the edit is chosen to be: a **safe extension** in brief D-11's own vocabulary — a new node
on a new path, adding nothing to Σ and changing no existing contract — so that the freshness
gate is shown failing on the mildest change there is. A gate that only noticed dramatic edits
would be the wrong gate. The canonical breaking cases and the N ≥ 5 evolution sequence are
SD-08's; nothing here stands in for them.

**Never-invokes (WA-07).** The added node's body is a sentinel of the same shape as the
fixture's own — it records itself in :data:`~tests.sample_workflows.travel_booking.TRIPPED` and
raises a ``BaseException`` subclass, so no ``except Exception`` on an extraction path can
swallow it into a warning. Extraction reaches it never; a run that did fails loudly.
"""

from __future__ import annotations

from typing import Any

from tests.sample_workflows.travel_booking import (
    TravelBookingSentinelError,
    TravelState,
    build_travel_booking_agent,
)

__all__ = ["AUDIT_NODE", "build_travel_booking_agent_with_audit"]

#: The node the edited agent adds. Named for what it would do, and it never does it.
AUDIT_NODE = "audit_trail"


def _write_audit_trail(state: TravelState) -> dict[str, str]:
    """The added node's body — records itself and raises, exactly like the fixture's own."""
    from tests.sample_workflows.travel_booking import TRIPPED

    del state
    TRIPPED.append(AUDIT_NODE)
    raise TravelBookingSentinelError(f"{AUDIT_NODE!r} was invoked — nothing here may ever run")


def build_travel_booking_agent_with_audit() -> Any:
    """v1 with :data:`AUDIT_NODE` on a new path between ``compile_itinerary`` and ``notify_traveler``.

    One node and two edges: topology moves (S) and the new node brings a contract slot with it
    (F). Σ is untouched, so E does not move — which is what makes the diff a freshness message
    prints on this pair a specific and checkable ``S, F``.

    Returned as the builder, at the same extraction level v1 is snapshotted at: PD-023 D4 makes
    a builder and its compiled form different documents, so comparing across levels would
    report a change that is only a change of level.
    """
    builder = build_travel_booking_agent()
    builder.add_node(AUDIT_NODE, _write_audit_trail)
    builder.add_edge("compile_itinerary", AUDIT_NODE)
    builder.add_edge(AUDIT_NODE, "notify_traveler")
    return builder
