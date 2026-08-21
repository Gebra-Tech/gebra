"""The first-``extract()`` version check (VERSION-COMPAT §4) — EX-12.

Normative authority: the VERSION-COMPAT living document §1 (ranges, the three frozen pair cells)
and §4 (the import-time-never-fails check). Covers the two acceptance claims: simulated
substrate combinations produce the specified warning classes, and importing ``gebra`` never
raises on version grounds.
"""

from __future__ import annotations

import subprocess
import sys
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from gebra.extraction import ExtractionWarningCode
from gebra.extraction.compat import (
    CompatClass,
    GebraVersionWarning,
    SubstrateVersions,
    _parse_leading_version,
    check_version_once,
    classify_substrate,
    out_of_range_warning,
    read_installed_versions,
    reset_version_check_cache,
)
from gebra.extraction.dispatch import extract
from tests.sample_workflows import sentinel_graph

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolated_version_cache() -> Iterator[None]:
    """Every test in this module starts and ends with no memoized classification.

    Setup clears whatever an earlier test file's ``extract()`` calls memoized (the real
    substrate, computed once and left cached — see the module's own docstring on why that
    is by design in production and a hazard in a shared test process). Teardown clears
    whatever *this* test computed or simulated, so the next test file's first ``extract()``
    call recomputes from the real, unpatched :func:`read_installed_versions` rather than
    inheriting a simulated out-of-range or untested result — which would otherwise leak a
    spurious ``unsupported-construct`` warning into unrelated conformance-golden tests.
    """
    reset_version_check_cache()
    yield
    reset_version_check_cache()


def _versions(
    *,
    python: tuple[int, int] = (3, 13),
    langgraph: tuple[int, int, int],
    langchain_core: tuple[int, int, int],
) -> SubstrateVersions:
    return SubstrateVersions(
        python=python,
        langgraph=langgraph,
        langchain_core=langchain_core,
        langgraph_raw=".".join(map(str, langgraph)),
        langchain_core_raw=".".join(map(str, langchain_core)),
    )


# ── classify_substrate: the three tested cells, in-range-untested, out-of-range ──────────


@pytest.mark.parametrize(
    ("langgraph", "langchain_core"),
    [
        ((1, 0, 0), (1, 0, 0)),
        ((1, 0, 10), (1, 1, 9)),
        ((1, 1, 0), (1, 2, 0)),
        ((1, 1, 9), (1, 3, 9)),
        ((1, 2, 0), (1, 4, 7)),
        ((1, 2, 10), (1, 5, 3)),
    ],
)
def test_each_frozen_cell_classifies_as_tested(
    langgraph: tuple[int, int, int], langchain_core: tuple[int, int, int]
) -> None:
    """A pairing inside one of §1's three frozen cells, on a tested Python, is TESTED."""
    versions = _versions(langgraph=langgraph, langchain_core=langchain_core)

    assert classify_substrate(versions) is CompatClass.TESTED


@pytest.mark.parametrize("python", [(3, 10), (3, 11), (3, 12), (3, 13)])
def test_every_tested_python_minor_is_tested(python: tuple[int, int]) -> None:
    """All four §3 Python minors classify as TESTED against a frozen cell."""
    versions = _versions(python=python, langgraph=(1, 2, 10), langchain_core=(1, 5, 3))

    assert classify_substrate(versions) is CompatClass.TESTED


@pytest.mark.parametrize(
    ("langgraph", "langchain_core", "why"),
    [
        ((1, 0, 5), (1, 3, 0), "langgraph cell-1 band paired with a cell-2 core"),
        ((1, 1, 5), (1, 0, 0), "langgraph cell-2 band paired with a cell-1 core"),
        ((1, 3, 0), (1, 5, 0), "langgraph past the 1.2.x band this build tests"),
        ((1, 2, 0), (1, 4, 6), "core one patch short of the 1.4.7 floor"),
    ],
)
def test_an_untested_pairing_is_in_range_untested(
    langgraph: tuple[int, int, int], langchain_core: tuple[int, int, int], why: str
) -> None:
    """Both packages individually in ``>=1.0,<2.0`` but not a *paired* tested cell (§1)."""
    versions = _versions(langgraph=langgraph, langchain_core=langchain_core)

    assert classify_substrate(versions) is CompatClass.IN_RANGE_UNTESTED, why


def test_a_python_above_the_tested_ceiling_is_in_range_untested() -> None:
    """§4's own example: Python 3.14 with an otherwise-tested pair warns, never fails."""
    versions = _versions(python=(3, 14), langgraph=(1, 2, 10), langchain_core=(1, 5, 3))

    assert classify_substrate(versions) is CompatClass.IN_RANGE_UNTESTED


@pytest.mark.parametrize(
    ("langgraph", "langchain_core", "python"),
    [
        ((0, 6, 5), (1, 5, 3), (3, 13)),
        ((2, 0, 0), (1, 5, 3), (3, 13)),
        ((1, 2, 10), (0, 9, 0), (3, 13)),
        ((1, 2, 10), (2, 0, 0), (3, 13)),
        ((1, 2, 10), (1, 5, 3), (3, 9)),
    ],
)
def test_outside_the_declared_range_is_out_of_range(
    langgraph: tuple[int, int, int], langchain_core: tuple[int, int, int], python: tuple[int, int]
) -> None:
    """langgraph/core outside ``>=1.0,<2.0``, or Python below the 3.10 floor — never tested."""
    versions = _versions(python=python, langgraph=langgraph, langchain_core=langchain_core)

    assert classify_substrate(versions) is CompatClass.OUT_OF_RANGE


def test_a_prerelease_of_the_next_major_is_out_of_range() -> None:
    """``2.0.0a1`` parses to ``(2, 0, 0)`` — an alpha already carries the next major's surface."""
    versions = _versions(langgraph=(2, 0, 0), langchain_core=(1, 5, 3))
    # The parser itself is exercised in test_read_installed_versions_parses_real_metadata;
    # here the point is only that the out-of-range verdict follows from the parsed tuple.
    assert versions.langgraph == (2, 0, 0)
    assert classify_substrate(versions) is CompatClass.OUT_OF_RANGE


# ── read_installed_versions: the live substrate, parsed ──────────────────────────────────


def test_read_installed_versions_parses_real_metadata() -> None:
    """Against whatever is actually installed: two well-formed three-tuples."""
    versions = read_installed_versions()

    assert versions.python == sys.version_info[:2]
    assert len(versions.langgraph) == 3
    assert len(versions.langchain_core) == 3
    assert all(isinstance(component, int) for component in versions.langgraph)
    assert all(isinstance(component, int) for component in versions.langchain_core)
    # The raw strings are what a report would show a person; they start with their parsed
    # tuple's own major.minor, which is what makes the two representations agree.
    assert versions.langgraph_raw.startswith(f"{versions.langgraph[0]}.{versions.langgraph[1]}")
    assert versions.langchain_core_raw.startswith(
        f"{versions.langchain_core[0]}.{versions.langchain_core[1]}"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2.10", (1, 2, 10)),
        ("1.4.0rc1", (1, 4, 0)),
        ("2.0.0a1", (2, 0, 0)),
        ("1.0", (1, 0, 0)),
        ("1.2.3+local", (1, 2, 3)),
    ],
)
def test_leading_version_parsing_discards_prerelease_and_local_suffixes(
    raw: str, expected: tuple[int, int, int]
) -> None:
    """A prerelease/local suffix never changes which cell/range a version lands in."""
    assert _parse_leading_version(raw) == expected


# ── check_version_once: memoized, warn-once ───────────────────────────────────────────────


def test_check_version_once_warns_exactly_once_for_an_untested_pairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two calls in a row: one `GebraVersionWarning`, not two — the warn-once policy."""
    fake = _versions(langgraph=(1, 0, 5), langchain_core=(1, 3, 0))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = check_version_once()
        second = check_version_once()

    assert first is second
    assert first.compat is CompatClass.IN_RANGE_UNTESTED
    version_warnings = [w for w in caught if issubclass(w.category, GebraVersionWarning)]
    assert len(version_warnings) == 1, caught


def test_check_version_once_never_warns_for_an_out_of_range_pairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out-of-range carries no Python warning at all — the fact rides the envelope instead."""
    fake = _versions(langgraph=(2, 0, 0), langchain_core=(1, 5, 3))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = check_version_once()

    assert result.compat is CompatClass.OUT_OF_RANGE
    assert not any(issubclass(w.category, GebraVersionWarning) for w in caught)


def test_check_version_once_never_warns_when_tested(monkeypatch: pytest.MonkeyPatch) -> None:
    """The conforming case is silent."""
    fake = _versions(langgraph=(1, 2, 10), langchain_core=(1, 5, 3))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = check_version_once()

    assert result.compat is CompatClass.TESTED
    assert caught == []


def test_out_of_range_warning_is_a_structured_unsupported_construct_record() -> None:
    """The record :func:`gebra.extraction.dispatch.extract` attaches — never a bare string.

    Carries the same four canonical keys every other ``unsupported-construct`` emitter in
    the tree uses (``construct``, ``location``, ``why``, ``ir_partial`` —
    :mod:`gebra.extraction.builder`, ``.compiled``, ``.lcel``, ``.state``, ``.digests``),
    plus the version facts themselves — never a bespoke shape for this one code.
    """
    versions = _versions(langgraph=(2, 0, 0), langchain_core=(1, 5, 3))

    warning = out_of_range_warning(versions)

    assert warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    assert warning.node is None
    assert warning.detail["construct"] == "substrate-version"
    assert warning.detail["location"] == {}
    assert isinstance(warning.detail["why"], str) and warning.detail["why"]
    assert warning.detail["ir_partial"] is False
    assert warning.detail["langgraph"] == "2.0.0"
    assert warning.detail["langchain_core"] == "1.5.3"
    assert warning.detail["python"] == "3.13"


# ── End-to-end through gebra.extraction.dispatch.extract ─────────────────────────────────


def test_extract_warns_gebra_version_warning_once_for_an_untested_pairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two ``extract()`` calls: the first warns, the second is silent — one process, one warn."""
    fake = _versions(langgraph=(1, 0, 5), langchain_core=(1, 3, 0))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)
    builder = sentinel_graph.build_sentinel_graph()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        extract(builder)
        extract(builder)

    version_warnings = [w for w in caught if issubclass(w.category, GebraVersionWarning)]
    assert len(version_warnings) == 1, caught


def test_extract_never_raises_for_an_untested_pairing(monkeypatch: pytest.MonkeyPatch) -> None:
    """In-range-but-untested proceeds — it warns, it never fails (§4)."""
    fake = _versions(langgraph=(1, 0, 5), langchain_core=(1, 3, 0))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)
    builder = sentinel_graph.build_sentinel_graph()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        envelope = extract(builder)

    assert envelope.ir.nodes  # extraction actually ran to completion


def test_extract_carries_unsupported_construct_on_every_call_when_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out-of-range attaches the version fact to *every* envelope, not just the first."""
    fake = _versions(langgraph=(2, 0, 0), langchain_core=(1, 5, 3))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)
    builder = sentinel_graph.build_sentinel_graph()

    first = extract(builder)
    second = extract(builder)

    for envelope in (first, second):
        version_facts = [
            w
            for w in envelope.warnings
            if w.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
            and w.detail.get("construct") == "substrate-version"
        ]
        assert len(version_facts) == 1, envelope.warnings


def test_extract_never_raises_for_an_out_of_range_substrate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out of range proceeds best-effort — it never fails either (§4)."""
    fake = _versions(langgraph=(2, 0, 0), langchain_core=(1, 5, 3))
    monkeypatch.setattr("gebra.extraction.compat.read_installed_versions", lambda: fake)
    builder = sentinel_graph.build_sentinel_graph()

    envelope = extract(builder)

    assert envelope.ir.nodes


def test_extract_on_the_real_substrate_carries_no_version_warning() -> None:
    """This dev environment's own substrate is a tested cell — the silent, conforming case."""
    builder = sentinel_graph.build_sentinel_graph()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        envelope = extract(builder)

    assert not any(issubclass(w.category, GebraVersionWarning) for w in caught)
    assert not any(
        w.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
        and w.detail.get("construct") == "substrate-version"
        for w in envelope.warnings
    )


# ── Import safety: never at import time, never a failure ─────────────────────────────────


def test_import_gebra_never_raises_on_version_grounds() -> None:
    """``import gebra`` alone, with warnings promoted to errors, still exits clean.

    If the version check ran at import time, an out-of-range or untested real substrate
    would turn ``-W error`` into a non-zero exit; it never does, because the check lives
    inside :func:`gebra.extraction.dispatch.extract` and nowhere near import.
    """
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", "import gebra"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_import_gebra_extraction_never_raises_on_version_grounds() -> None:
    """Same claim one level in: importing the extraction package itself never checks."""
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", "import gebra.extraction"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_bare_import_never_reaches_the_compat_module() -> None:
    """A stronger structural claim: ``import gebra`` never even loads ``gebra.extraction``.

    ``gebra/__init__.py``'s PEP 562 laziness (module docstring: "resolved lazily … the
    laziness is load-bearing") is what makes this true, and :mod:`gebra.extraction.compat`
    leans on it: its own eager import-time computation only runs once something actually
    imports :mod:`gebra.extraction`. Checked by ``sys.modules`` absence rather than by
    monkeypatching :func:`read_installed_versions` — a patch applied *after* importing
    ``gebra.extraction.compat`` (to reach the name to patch) would already be too late, since
    that import is what runs the eager computation this test means to catch never happening.
    """
    probe = "import gebra\nimport sys\nprint('gebra.extraction' in sys.modules)\n"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", result.stdout


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Network primitives raise from the first line; socket *construction* is
#: only counted until ``compat``'s own import completes, for the reason
#: ``tests/extraction/test_dispatch.py`` states about urllib3's IPv6 probe: importing the
#: substrate — reached here, since ``gebra.extraction.compat`` sits inside the
#: ``gebra.extraction`` package — runs library-level socket construction that has nothing to
#: do with this path. From there, everything is this module's own work: a second,
#: uncached :func:`~gebra.extraction.compat.read_installed_versions` call (proving the
#: *repeatable* metadata read — not just its cached first run — never reaches the network),
#: then a full :func:`~gebra.extraction.compat.check_version_once`.
_TRIPWIRE = """
import socket, sys

attempts = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _CountSocket(socket.socket):
    def __new__(cls, *a, **k):
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created while checking the substrate version")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

# This import is itself where compat.py's own eager classification runs (its module-level
# `_compute_version_check()`) -- placed inside the guarded region so that computation is
# checked here rather than assumed hazard-free because some other test's guard happened to
# cover it first.
import gebra.extraction.compat as compat

assert attempts == [], attempts
socket.socket = _TripSocket

# A second, uncached read: importlib.metadata's `.metadata` property re-runs its deferred
# `from . import _adapters` on every call regardless of what is already cached (see the
# module docstring's "one import-time side effect" section) -- this is what proves a *repeat*
# metadata read is exactly as network-free as the first one, not just incidentally so.
versions = compat.read_installed_versions()
result = compat.check_version_once()
assert result.versions == versions
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_version_check_opens_no_socket_and_resolves_no_name() -> None:
    """The WA-07 claim for this card's path, in a fresh interpreter.

    ``read_installed_versions``/``check_version_once`` read installed-distribution metadata
    off disk (``importlib.metadata``) and ``sys.version_info`` — nothing that should ever
    reach a socket or a name resolution. This runs both, twice each (module import plus an
    explicit second call), under a guard where every network primitive raises, and asserts
    nothing was reached.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        (
            "socket.create_connection(('example.invalid', 80))\n",
            "create_connection was reached",
        ),
    ],
    ids=["socket", "getaddrinfo", "gethostbyname", "create_connection"],
)
def test_each_network_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — each raiser gets its own control."""
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_a_swallowed_trip_still_fails_the_run() -> None:
    """Recording before raising is what makes a ``try: … except: pass`` path visible."""
    swallow = "\ntry:\n    socket.getaddrinfo('example.invalid', 80)\nexcept Exception:\n    pass\n"

    result = _run_guarded(swallow)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['getaddrinfo']", result.stdout
