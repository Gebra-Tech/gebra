"""Armed targets for the CLI's live-target resolution seam (CLI-04; CLI-SPEC §0.5 item 3).

``gebra verify <module>:<attribute>`` is one of the three verbs that can reach a live
object, and §0.5 item 3 fixes the tripwire shape its card must land: a sentinel target
module exercised **through the CLI's own entry point**, arming at least the four points
this module arms —

* **node callables in the returned graph** (:data:`graph`'s two nodes, and the graph
  :func:`build_graph` returns) — extraction reads them and never runs them;
* **an attribute that is a zero-argument callable but not a graph factory**
  (:func:`launch_app`) — pinning §2.4's refusal to call anything without ``--call``;
* **an attribute whose callable needs arguments** (:func:`needs_args`) — pinning the
  exit-2 refusal when ``--call``'s one no-argument call cannot succeed;
* **an import-time marker** (:data:`IMPORTED`) — so §2.4 step 1's "the module's top-level
  code runs" concession is observed rather than assumed.

Every armed callable **records the call before raising**, and the sentinel derives from
:class:`BaseException`, so a guard written as ``except Exception`` anywhere on the path
cannot turn an execution into a warning — the same design, for the same reason, as
``tests/sample_workflows/sentinel_resolution.py``. Assertions belong on the ledgers
(:data:`TRIPPED`, :data:`FACTORY_CALLS`), never on the exit code, which CLI-SPEC §3.4
makes uninformative here by mapping an escaping exception to a specified exit ``2``.

Importing this module **builds** one small graph and runs nothing: the one module-level
workflow object is what §2.4's refusal message tells users to write ("construction happens
at import"), so the blessed layout is also the fixture.
"""

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

#: The §2.4 step-1 marker: importing this module appends here, once per interpreter.
IMPORTED: Final[list[str]] = []

#: Every armed callable that was invoked, in order. Extraction reads; this stays empty.
TRIPPED: Final[list[str]] = []

#: Every call of :func:`build_graph` — the ``--call`` opt-in's own ledger. A CLI run
#: without ``--call`` must leave this empty too; with it, exactly one entry per run.
FACTORY_CALLS: Final[list[str]] = []

IMPORTED.append(__name__)


class CliSentinelError(BaseException):
    """Raised by every armed callable here that gets invoked.

    Deliberately **not** an :class:`Exception`: the CLI maps any escaping exception to a
    specified exit ``2`` (CLI-SPEC §3.4), and resolution guards catch ``Exception`` around
    the user-code steps it licenses — so only a ``BaseException`` makes an execution end
    the run instead of dressing it as a refusal, and only the ledger makes it assertable.
    """


def _arm(label: str) -> Any:
    """Record the invocation, then refuse to run — the first statement of every body."""
    TRIPPED.append(label)
    raise CliSentinelError(f"{label!r} was invoked — the CLI resolves and extracts, it never runs")


class PipelineState(TypedDict):
    """A two-key state, enough for a well-formed two-node chain."""

    query: str
    answer: str


def fetch_context(state: PipelineState) -> dict[str, Any]:
    """A node body. Never runs."""
    _arm("fetch_context")
    return {"answer": "…"}


def draft_answer(state: PipelineState) -> dict[str, Any]:
    """A second node body. Never runs."""
    _arm("draft_answer")
    return {"answer": "…"}


def _build() -> "StateGraph[PipelineState]":
    builder: StateGraph[PipelineState] = StateGraph(PipelineState)
    builder.add_node("fetch_context", fetch_context)
    builder.add_node("draft_answer", draft_answer)
    builder.add_edge(START, "fetch_context")
    builder.add_edge("fetch_context", "draft_answer")
    builder.add_edge("draft_answer", END)
    return builder


#: The module-level workflow object — §2.4's blessed layout, resolvable with no call.
graph: Final = _build()


def build_graph() -> "StateGraph[PipelineState]":
    """A zero-argument graph factory — the shape ``--call`` exists for.

    Records the call (that is the licensed, asked-for execution) and returns a fresh graph
    whose node bodies are armed, so the run also shows extraction executing none of them.
    """
    FACTORY_CALLS.append("build_graph")
    return _build()


def launch_app() -> None:
    """A zero-argument callable that is **not** a graph factory — an application entry.

    Without ``--call`` the CLI must refuse to call it (§2.4 step 3); with ``--call`` the
    user asked for the call by name, and the recorded invocation is the licensed one.
    """
    _arm("launch_app")


def needs_args(config: str) -> None:
    """A callable that requires an argument — ``--call``'s one no-argument call raises.

    The body is armed but unreachable through the CLI: Python refuses the empty call at
    binding time, so :data:`TRIPPED` stays clean and the CLI reports the exception as the
    §2.6 input-stage refusal.
    """
    _arm("needs_args")


#: An attribute that is no workflow object and not callable — §2.4's plain refusal case.
not_a_workflow: Final = {"nodes": "this is a dict, not a graph"}
