"""The same node shapes under ``from __future__ import annotations`` (ANNOTATION §4).

Its own module because the future import is per-file and turns **every** annotation in it into
a string. That is exactly the case §4's no-evaluation rule decides — resolving a string
annotation means evaluating it, and DEC-08 rules that out — so the two annotation patterns
have to withdraw here while the body patterns keep working unchanged.

PEP 563 is not a corner case: it is one line at the top of a module, and a project that has it
has it everywhere. A build whose inference silently stopped reading annotations under it, or
started calling :func:`typing.get_type_hints` to get them back, would be caught here.

Nothing here imports langgraph, opens a socket, or executes anything.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict


class FutureSentinelError(RuntimeError):
    """Raised by any node here that gets called."""


def _arm(label: str, *values: object) -> Any:
    """Refuse to run, whatever it is handed."""
    raise FutureSentinelError(f"{label!r} was invoked — inference reads source, never runs it")


class FutureState(TypedDict):
    """The graph's full state schema, in a module with the future import."""

    query: str
    plan: str


class FutureReads(TypedDict):
    """A projection that inference cannot see through a string annotation."""

    query: str


def annotated_under_future_import(state: FutureReads) -> FutureWrites:
    """The annotations are strings here, so only the body patterns apply."""
    _arm("annotated_under_future_import")
    return {"plan": _arm("plan", state["query"])}


class FutureWrites(TypedDict):
    """Declared *after* the node that returns it — legal only because of the future import,
    which is the other half of why a string annotation cannot simply be looked up."""

    plan: str


#: The graph's own schema object, for the §4 exclusion.
FULL_STATE_SCHEMAS: Final[tuple[type, ...]] = (FutureState,)
