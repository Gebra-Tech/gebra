"""Import targets for the CLI suite that the sentinel module has no reason to carry.

Kept separate from :mod:`tests.sample_workflows.sentinel_cli` on purpose: everything there
is armed and ledgered for the never-invokes claim, while these exist to construct ordinary
§2.6 refusals through the entry point.
"""

from typing import Any, TypedDict

from langgraph.graph import StateGraph


class EmptyState(TypedDict):
    """A state schema for a graph that will hold no nodes."""

    query: str


def build_empty_graph() -> "StateGraph[EmptyState]":
    """A builder with an empty node set — ``extract()`` refuses it at its own boundary
    (INTROSPECTION-SPEC §2's one degenerate-input exception), which through the CLI is the
    §2.6 ``extraction``-stage tool error."""
    return StateGraph(EmptyState)


#: Not a workflow object and not callable — §2.4 step 3's plain refusal.
plain_data: dict[str, Any] = {"kind": "not a graph"}
