"""Never-invokes tripwire index (decisions D-018/D-023; INTROSPECTION-SPEC §1; WA-07).

Extraction never invokes user code: no node function, router, tool, or LLM is called by
``gebra.extract()``, and no network connection is opened. The two tests here are the
smallest end-to-end statement of that — importing (and thereby building) the sentinel graph
trips nothing, and extracting it trips nothing either.

Every landed extraction path carries its own tripwire, and each path's guarded child makes
the claim in a fresh interpreter where sockets, name resolution and ``StateGraph.compile``
all raise. **The canonical, machine-checked index of those tripwires is
``tests/never_invokes_audit.md``** — the path-to-tripwire audit table, reconciled against
``src/gebra/extraction/`` by :func:`test_the_audit_table_lists_every_extraction_path` below.
That table is where a reviewer answers "does every landed path have a tripwire?", and a path
that lands adds its row there in the same commit rather than duplicating the list here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXTRACTION = _REPO_ROOT / "src" / "gebra" / "extraction"
_AUDIT = _REPO_ROOT / "tests" / "never_invokes_audit.md"

#: Extraction paths with a dedicated guarded-subprocess tripwire, module → its tripwire test.
#: The audit table renders this for humans; the test below reconciles both against the package
#: on disk, so a path that lands without a row — or a row naming a file that is gone — fails.
_GUARDED_PATHS: dict[str, str] = {
    "dispatch": "tests/extraction/test_dispatch.py",
    "builder": "tests/extraction/test_builder.py",
    "routing": "tests/extraction/test_routing.py",
    "state": "tests/extraction/test_state.py",
    "contracts": "tests/extraction/test_contracts.py",
    "compiled": "tests/extraction/test_compiled.py",
    "lcel": "tests/extraction/test_lcel.py",
    "digests": "tests/extraction/test_digests.py",
    "stock": "tests/extraction/test_digests.py",
    "compat": "tests/extraction/test_compat.py",
}

#: Substrate-reaching paths whose never-invokes claim is asserted under another module's guard.
_SHARED_PATHS: dict[str, str] = {
    "inference": "tests/extraction/test_contracts.py",
}

#: Modules that read no live workflow object — IR/envelope/warning data and the sidecar seam —
#: so there is no body for them to invoke. The ``gebra.toml`` loader itself is guarded by
#: ``tests/annotations/test_sidecar.py``; this ``sidecar.py`` only builds records from it.
_DATA_ONLY_MODULES: frozenset[str] = frozenset(
    {"base", "envelope", "errors", "warnings", "sidecar"}
)


def test_import_is_side_effect_free() -> None:
    """Importing (and thereby building) the sentinel graph trips no sentinel."""
    from tests.sample_workflows import sentinel_graph

    assert sentinel_graph.SENTINEL_GRAPH is not None
    # Rebuilding is equally side-effect-free: registering nodes never calls them.
    builder = sentinel_graph.build_sentinel_graph()
    assert set(builder.nodes) == {"plan_step", "act_step", "summarize_step"}


def test_extract_never_invokes() -> None:
    """gebra.extract() over the sentinel graph must not call any node or router.

    The end-to-end claim, now live: the builder path is registered, so this runs a
    real extraction rather than reaching a refusal. Every node function and router
    in the sentinel graph raises if it is called, so a pass means none of them was
    — and the returned IR is checked to be the graph's, so an extraction that
    somehow produced nothing could not pass quietly.

    This test's scope is deliberately the one line the module is named for. The
    guarded-interpreter version of the same claim — where sockets, name resolution
    and ``StateGraph.compile`` all raise — is
    ``tests/extraction/test_builder.py::test_builder_extraction_invokes_nothing_and_compiles_nothing``.
    """
    import gebra
    from tests.sample_workflows import sentinel_graph

    try:
        envelope = gebra.extract(sentinel_graph.SENTINEL_GRAPH)
    except sentinel_graph.SentinelExecutedError as exc:
        pytest.fail(f"extraction invoked user code: {exc}")

    assert [node.id for node in envelope.ir.nodes] == ["act_step", "plan_step", "summarize_step"]


def test_the_audit_table_lists_every_extraction_path() -> None:
    """Reconcile the audit table against ``src/gebra/extraction/`` — the anti-duplication check.

    The index used to be a prose list in this module's docstring, which drifts. It is now the
    audit table, and this test is what keeps it honest: every extraction module is classified
    exactly once (guarded, shared, or data-only), every named tripwire file exists, and the
    table renders every module and every guarded test file. A path that lands without a row
    fails here rather than being silently uncovered.
    """
    modules = {path.stem for path in _EXTRACTION.glob("*.py") if path.stem != "__init__"}
    classified = set(_GUARDED_PATHS) | set(_SHARED_PATHS) | set(_DATA_ONLY_MODULES)

    # Exactly-once classification: every module accounted for, none classified two ways.
    assert modules == classified, {
        "unclassified_modules": sorted(modules - classified),
        "classified_but_absent": sorted(classified - modules),
    }
    # Pairwise-disjoint, enforced by count: if any module sat in two sets the summed size would
    # exceed the union's. A 3-way intersection would miss a module classified in only two.
    assert len(_GUARDED_PATHS) + len(_SHARED_PATHS) + len(_DATA_ONLY_MODULES) == len(classified)

    # Every named tripwire file exists.
    for module, test_file in {**_GUARDED_PATHS, **_SHARED_PATHS}.items():
        assert (_REPO_ROOT / test_file).is_file(), f"{module}: missing tripwire {test_file}"

    # The audit table renders every module and every guarded test file, so the human-readable
    # table cannot omit what this test authorizes.
    audit = _AUDIT.read_text(encoding="utf-8")
    for module in modules:
        assert f"`{module}.py`" in audit, f"audit table omits src/gebra/extraction/{module}.py"
    for test_file in {**_GUARDED_PATHS, **_SHARED_PATHS}.values():
        assert Path(test_file).name in audit, f"audit table omits {test_file}"
