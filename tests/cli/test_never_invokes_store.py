"""WA-07 tripwires for CLI-05's two live-target paths — §0.5 item 3, through ``main()``.

CLI-SPEC §0.5's per-path table assigns two rows to this card: ``gebra snapshot`` over a
live target, and ``gebra diff`` with one or both sides a live target — including the mixed
case where one side is a stored label and the other an import reference (§7). The sentinel
module is CLI-04's :mod:`tests.sample_workflows.sentinel_cli`, unchanged: the same four
arms (node callables in the resolved graph; a zero-argument non-factory callable; a
callable needing arguments under ``--call``; the import-time marker), the same
``BaseException``-derived sentinel that records before raising, and every assertion on the
**ledgers** — never on the exit code, which §3.4 makes uninformative by mapping an
escaping exception to a specified exit ``2``.

Beyond the four arms, two sentences of §4.2/§4.3 with execution consequences are pinned on
the ``--call`` ledger, because only a call count can state them: the snapshot verb's
eligibility run and write share **one** resolution (one factory call per invocation, not
two), and each diff side resolves independently, exactly once — with no side resolved at
all once the run is already dead.

These verbs add no extraction path: resolution is CLI-04's ``gebra.cli.resolve`` (the
§2.4 boundary, held by ``tests/cli/test_never_invokes.py``'s guarded interpreters), and
everything after it is ``extract()``'s frozen read-only introspection. What this file owes
is the observation that the two *new verbs* drive that boundary and nothing more.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from gebra.cli import main
from gebra.store import SnapshotStore
from tests.sample_workflows import sentinel_cli

REPO_ROOT = Path(__file__).parent.parent.parent

MODULE = "tests.sample_workflows.sentinel_cli"


@pytest.fixture(autouse=True)
def _clean_ledgers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Clear the ledgers, make the sentinel importable, and give each test its own cwd —
    the store-facing verbs write, and a store must never leak between tests."""
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    monkeypatch.chdir(tmp_path)
    sentinel_cli.TRIPPED.clear()
    sentinel_cli.FACTORY_CALLS.clear()
    yield
    sentinel_cli.TRIPPED.clear()
    sentinel_cli.FACTORY_CALLS.clear()


def _run(*argv: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _seed_store(capsys: pytest.CaptureFixture[str]) -> SnapshotStore:
    """A store holding the sentinel graph's own content as ``1.0.0.0`` — through the verb,
    so the seeding is itself the snapshot path under the sentinel."""
    code, _, _ = _run("snapshot", f"{MODULE}:graph", "--store", ".gebra", capsys=capsys)
    assert code == 0
    store = SnapshotStore(Path.cwd() / ".gebra")
    assert store.versions() == ("1.0.0.0",)
    return store


# ── gebra snapshot over a live target (§0.5 item 3, row 2) ───────────────────────────────


def test_snapshotting_a_module_level_graph_executes_no_node_body(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 1: the whole extract → gate → write path runs and both ledgers stay empty.

    The recorded snapshot is asserted to hold the sentinel graph's node set, so a run that
    silently stopped reaching the object would fail here rather than pass quietly.
    """
    store = _seed_store(capsys)

    assert sentinel_cli.TRIPPED == []
    assert sentinel_cli.FACTORY_CALLS == []
    stored = store.read("1.0.0.0")
    assert {node.id for node in stored.ir.nodes} == {"fetch_context", "draft_answer"}
    assert stored.extracted_from.source == f"{MODULE}:graph"


def test_snapshot_without_call_never_calls_the_attribute(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 2: a zero-argument callable that is no factory is refused, uncalled — and
    nothing is recorded of it."""
    code, _, err = _run("snapshot", f"{MODULE}:launch_app", "--store", ".gebra", capsys=capsys)

    assert sentinel_cli.TRIPPED == []
    assert sentinel_cli.FACTORY_CALLS == []
    assert code == 2
    assert "did not call it" in err
    assert not (Path.cwd() / ".gebra").exists()


def test_snapshot_call_needing_arguments_is_refused_with_the_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 3: ``--call`` makes one no-argument call; Python refuses at binding, the body
    never runs, and the diagnostic reports the ``TypeError``."""
    code, _, err = _run(
        "snapshot", "--call", f"{MODULE}:needs_args", "--store", ".gebra", capsys=capsys
    )

    assert sentinel_cli.TRIPPED == []
    assert code == 2
    assert "TypeError" in err


def test_snapshot_call_resolves_once_for_the_gate_and_the_write(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """§4.2's "a ``--call`` attribute is called at most once per invocation", on the
    ledger: the eligibility run and the store write share one resolution, so the factory
    ledger grows by exactly one entry — not one for the gate and one for the write."""
    code, _, _ = _run(
        "snapshot", "--call", f"{MODULE}:build_graph", "--store", ".gebra", capsys=capsys
    )

    assert sentinel_cli.FACTORY_CALLS == ["build_graph"]
    assert sentinel_cli.TRIPPED == []
    assert code == 0
    assert SnapshotStore(Path.cwd() / ".gebra").versions() == ("1.0.0.0",)


def test_snapshot_performs_the_import_itself_on_a_fresh_module(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arm 4: the §2.4 step-1 concession — the module's top-level code runs — observed on
    a module this interpreter had not imported, not assumed from a cache hit."""
    monkeypatch.delitem(sys.modules, MODULE)
    code, _, _ = _run("snapshot", f"{MODULE}:graph", "--store", ".gebra", capsys=capsys)

    fresh = importlib.import_module(MODULE)
    assert fresh is not sentinel_cli, "the CLI was handed the cached module, not a fresh one"
    assert fresh.IMPORTED == [MODULE]
    assert fresh.TRIPPED == []
    assert code == 0


# ── gebra diff with a live side (§0.5 item 3, row 3 — the mixed case included) ───────────


def test_the_mixed_diff_reads_the_live_side_and_runs_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """§7's named case: one side a stored label, the other an import reference. The
    comparison completes — against the stored copy of the same graph, so "nothing moved"
    is the output that proves the live object was reached — and both ledgers stay empty."""
    _seed_store(capsys)
    sentinel_cli.TRIPPED.clear()
    sentinel_cli.FACTORY_CALLS.clear()

    code, out, _ = _run("diff", "1.0.0.0", f"{MODULE}:graph", "--store", ".gebra", capsys=capsys)

    assert sentinel_cli.TRIPPED == []
    assert sentinel_cli.FACTORY_CALLS == []
    assert code == 0
    assert "nothing moved" in out


def test_a_two_sided_call_diff_calls_each_factory_exactly_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """§4.3: ``--call`` applies to every import-reference side, and each side resolves
    independently — two sides, two entries on the factory ledger, node bodies untouched."""
    code, out, _ = _run(
        "diff", f"{MODULE}:build_graph", f"{MODULE}:build_graph", "--call", capsys=capsys
    )

    assert sentinel_cli.FACTORY_CALLS == ["build_graph", "build_graph"]
    assert sentinel_cli.TRIPPED == []
    assert code == 0
    assert "nothing moved" in out  # two builds of one definition carry one digest


def test_diff_without_call_never_calls_a_live_side(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 2 on the diff path: the non-factory attribute side is refused, uncalled."""
    _seed_store(capsys)
    sentinel_cli.TRIPPED.clear()
    sentinel_cli.FACTORY_CALLS.clear()

    code, _, err = _run(
        "diff", f"{MODULE}:launch_app", "1.0.0.0", "--store", ".gebra", capsys=capsys
    )

    assert sentinel_cli.TRIPPED == []
    assert sentinel_cli.FACTORY_CALLS == []
    assert code == 2
    assert "BEFORE" in err


def test_a_dead_run_resolves_no_further_side(capsys: pytest.CaptureFixture[str]) -> None:
    """Sides resolve in order and the first failure stops the run: with BEFORE
    unresolvable, the AFTER factory is never imported into a call — no user code runs for
    a comparison that can no longer happen."""
    code, _, _ = _run("diff", "missing.ir.yaml", f"{MODULE}:build_graph", "--call", capsys=capsys)

    assert sentinel_cli.FACTORY_CALLS == []
    assert sentinel_cli.TRIPPED == []
    assert code == 2


def test_diff_call_needing_arguments_is_refused_with_the_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 3 on the diff path: the one no-argument call cannot bind, the body never runs,
    and the diagnostic reports the ``TypeError`` on the side that failed."""
    _seed_store(capsys)
    sentinel_cli.TRIPPED.clear()
    sentinel_cli.FACTORY_CALLS.clear()

    code, _, err = _run(
        "diff", f"{MODULE}:needs_args", "1.0.0.0", "--store", ".gebra", "--call", capsys=capsys
    )

    assert sentinel_cli.TRIPPED == []
    assert sentinel_cli.FACTORY_CALLS == []
    assert code == 2
    assert "TypeError" in err and "BEFORE" in err


def test_diff_performs_the_import_itself_on_a_fresh_module(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arm 4 on the diff path: the store is seeded first (which imports the module), the
    module is then dropped from ``sys.modules``, and the diff's own resolution is observed
    performing the import — not a cache hit."""
    _seed_store(capsys)
    monkeypatch.delitem(sys.modules, MODULE)

    code, out, _ = _run("diff", "1.0.0.0", f"{MODULE}:graph", "--store", ".gebra", capsys=capsys)

    fresh = importlib.import_module(MODULE)
    assert fresh is not sentinel_cli, "the CLI was handed the cached module, not a fresh one"
    assert fresh.IMPORTED == [MODULE]
    assert fresh.TRIPPED == []
    assert code == 0
    assert "nothing moved" in out
