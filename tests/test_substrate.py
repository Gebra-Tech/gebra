"""The version predicates in :mod:`tests.substrate`, checked against the live substrate.

A version-conditional skip is only honest if its condition is true. These predicates are
derived from published release metadata (EX-17 read the wheels), and every one of them gates
a fixture or an expectation somewhere in the suite — so a boundary that is off by a minor
would silently skip a capability that is present, or run a fixture that cannot be built.
Each predicate is therefore re-derived here from the installed packages themselves and
compared with the table, on every cell of the VERSION-COMPAT §3 matrix.

Nothing here invokes a model or a node: ``bind()`` constructs a wrapper, and
:class:`~tests.sample_workflows.sentinel_digests.ArmedChatModel` raises if anything ever
calls it (WA-07).
"""

from __future__ import annotations

import inspect
import re

from langchain_core.runnables.base import RunnableBinding
from langgraph.graph import StateGraph

from tests import substrate
from tests.sample_workflows import sentinel_digests as sd


def test_the_node_defaults_predicate_matches_the_installed_builder() -> None:
    """``set_node_defaults`` is an attribute; its presence is the whole condition."""
    assert hasattr(StateGraph, "set_node_defaults") is substrate.HAS_NODE_DEFAULTS


def test_the_error_handler_predicate_matches_the_installed_builder() -> None:
    """Checked against the *signature*, not against a call.

    ``add_node`` takes ``**kwargs``, so passing ``error_handler=`` to a builder that has no
    such parameter is accepted and dropped. Presence in the signature is the only reading
    that distinguishes the two substrates.
    """
    parameters = inspect.signature(StateGraph.add_node).parameters

    assert ("error_handler" in parameters) is substrate.HAS_NODE_ERROR_HANDLER


def test_the_timeout_predicate_matches_the_installed_builder() -> None:
    """Same signature reading as ``error_handler`` — the ``**kwargs`` hazard is shared."""
    parameters = inspect.signature(StateGraph.add_node).parameters

    assert ("timeout" in parameters) is substrate.HAS_NODE_TIMEOUT


def test_the_delta_channel_predicate_matches_the_installed_package() -> None:
    """Whether ``langgraph.channels.delta`` exists — module presence, not an import-use.

    ``find_spec`` locates the module without executing it; on the 1.0/1.1 lines the module
    is simply not there.
    """
    from importlib.util import find_spec

    assert (find_spec("langgraph.channels.delta") is not None) is substrate.HAS_DELTA_CHANNEL


def test_the_binding_predicate_matches_what_bind_answers_with() -> None:
    """Whether ``bind()`` answers with a stock ``RunnableBinding`` or a subclass of one."""
    sd.TRIPPED.clear()

    binding = sd.ArmedChatModel(temperature=0.2).bind(stop=["x"])

    assert (type(binding) is not RunnableBinding) is substrate.CORE_BINDS_TO_A_SUBCLASS
    assert isinstance(binding, RunnableBinding)
    assert sd.TRIPPED == []


def test_the_metadata_predicate_matches_what_the_base_model_fills() -> None:
    """Whether ``BaseChatModel`` fills ``metadata`` itself, and with what."""
    sd.TRIPPED.clear()

    filled = sd.ArmedChatModel().metadata

    assert (filled is not None) is substrate.CORE_FILLS_LC_VERSIONS_METADATA
    if filled is not None:
        assert set(filled) == {"lc_versions"}
    assert sd.TRIPPED == []


def test_every_reason_names_an_api_and_the_minor_that_introduced_it() -> None:
    """The acceptance condition EX-17 carries, asserted rather than reviewed.

    A skip reason that says only "unsupported version" hides which capability is missing.
    Every reason in the table names the API it needs and the release that introduced it, and
    reports what is installed so a reader of a skip report can tell the two apart.
    """
    reasons = [
        substrate.NODE_DEFAULTS_REASON,
        substrate.NODE_ERROR_HANDLER_REASON,
        substrate.NODE_TIMEOUT_REASON,
        substrate.DELTA_CHANNEL_REASON,
        substrate.CHAT_MODEL_BINDING_REASON,
        substrate.LC_VERSIONS_METADATA_REASON,
    ]

    for reason in reasons:
        assert "introduced in" in reason
        assert re.search(r"(langgraph|langchain-core) \d+\.\d+\.\d+", reason), reason
        assert "installed" in reason


def test_a_prerelease_version_gates_as_its_own_line() -> None:
    """The ``--pre`` cell installs prereleases; a prerelease carries its line's APIs."""
    match = substrate._RELEASE.match("1.6.0a1")

    assert match is not None
    assert match.groups() == ("1", "6", "0")
