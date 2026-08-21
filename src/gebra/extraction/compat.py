"""VERSION-COMPAT §4 — the first-``extract()`` version check.

Normative authority: the VERSION-COMPAT living document §1 (the ratified supported ranges and the
three frozen pair cells) and §4 ("Import-time check, never import-time failure"): on the
first ``gebra.extract()`` call, the installed substrate versions and the running Python are
compared to the tested matrix. In-range-but-untested — including a Python above the tested
3.13 ceiling — warns :class:`GebraVersionWarning`; out of range (langgraph/langchain-core
``>=2.0`` or ``<1.0``) proceeds best-effort, and the fact rides the envelope as an
``unsupported-construct`` extraction warning (INTROSPECTION-SPEC §2, §8) rather than as a
Python warning. **``import gebra`` never runs this check and never fails on version
grounds** — a bare ``import gebra`` never even reaches this module, let alone reads a
version or emits a warning (see ``tests/extraction/test_compat.py::``
``test_bare_import_never_reaches_the_compat_module`` and
``::test_import_gebra_never_raises_on_version_grounds``); what runs at *this* module's own
import, and why, is the module's next section.

**What "tested" means here** — three embedding choices this card
(``decisions_to_implementer``) makes, none of them the spec's own ruling:

* **"1.2.latest" reads as "the whole 1.2.x line".** §1's compatibility promise is
  "langgraph 1.2.latest + core >=1.4.7", and it is continuously extended by the §4
  ceiling-extension cadence ("on each new substrate release, run the §3 drift suite …
  green -> extend the tested matrix"). A runtime check has no patch-exact "latest" to
  compare an install against, so this module reads the promise as covering 1.2.x wholesale,
  up to (but excluding) 1.3.0 — which is exactly the boundary the promise's own next
  extension would move. A 1.3.x install is in-range-but-untested until that extension
  lands, which is the check doing its job rather than a gap in it.
* **Cell boundaries are the §1 bands, not the GOV-D3 exact CI pins.** GOV-D3/PD-030's
  candidate pins (e.g. ``langgraph==1.2.10`` + ``langchain-core==1.5.3``) are what the CI
  drift matrix installs per cell for byte-exact comparison — and PD-030's own ratification
  (2026-08-04) explicitly **tabled the pin table rather than ratifying it** alongside its
  Q1-Q3 rulings, so it is doubly not this check's authority: candidate even on its own
  terms, and not yet ratified even as a candidate. §1 states outright that "the §4 metadata
  ranges are the installability envelope, never the compatibility promise" and that
  per-cell pins are fixed by a *different* rule (§3's resolution rule). What a user's
  install is checked against here is the band the compatibility promise names, not one
  pinned patch inside it.
* **A sub-floor Python folds into out-of-range, symmetrically with the two named packages.**
  §4's text names "≥2.0 or <1.0" as langgraph/langchain-core's out-of-range shape and is
  silent on a sub-3.10 Python specifically — the declared floor is an installability
  requirement pip enforces, so the case is exotic (a ``--ignore-requires-python`` install,
  say). Treating it as :data:`CompatClass.OUT_OF_RANGE` rather than
  :data:`CompatClass.IN_RANGE_UNTESTED` is the same posture §4 states for the two packages,
  applied to the one other axis this check reads.

Nothing here imports langgraph or langchain-core — only their installed-distribution
*metadata* (``importlib.metadata.version``, never the packages themselves) and
``sys.version_info`` — and nothing here opens a socket or executes anything (WA-07).

**One import-time side effect, stated rather than left to surprise a WA-07 guard.**
``importlib.metadata``'s own ``Distribution.metadata`` property does ``from . import
_adapters`` **every time it runs**, deferred there deliberately by CPython for import cost
(python/cpython#109829) — so calling :func:`read_installed_versions` for the first time
*inside* a guarded extraction call is exactly the "a new module was imported" shape
``tests/extraction/test_state.py``'s tripwire exists to catch, and calling it there a second
time does not help: the relative import statement runs again regardless of what is already
cached. So the classification (:func:`classify_substrate` over the real
:func:`read_installed_versions`) is resolved once, right here, at this module's own import —
not truly lazily. What still waits for the very first ``extract()`` call is the *visible*
effect: whether :class:`GebraVersionWarning` fires at all, tracked separately in
:func:`check_version_once` so the computation above and the warning it may produce are two
different clocks. Nothing observable from outside this module tells the two designs apart —
no warning, no exception, no envelope field differs — so this is a WA-07 accommodation, not
a semantic change from what VERSION-COMPAT §4 describes. The eager computation is wrapped
defensively and can never make ``import gebra`` fail: if it does not resolve here,
:func:`check_version_once` simply resolves it lazily on its own first call instead.
"""

from __future__ import annotations

import contextlib
import re
import sys
import warnings
from dataclasses import dataclass
from enum import Enum
from importlib import metadata
from typing import Final

from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode

__all__ = [
    "CompatClass",
    "GebraVersionWarning",
    "SubstrateVersions",
    "VersionCheck",
    "check_version_once",
    "classify_substrate",
    "out_of_range_warning",
    "read_installed_versions",
    "reset_version_check_cache",
]


class GebraVersionWarning(UserWarning):
    """The installed substrate is in gebra's declared range but not a tested pairing (§4).

    A plain :mod:`warnings` category — never raised, so a caller filters or escalates it the
    ordinary way (``warnings.filterwarnings("error", category=gebra.GebraVersionWarning)``
    turns it into a hard failure for whoever wants that). ``import gebra`` never triggers
    it: it is emitted only from inside the first :func:`gebra.extraction.dispatch.extract`
    call in a process (see :func:`check_version_once`'s warn-once policy).
    """


class CompatClass(str, Enum):
    """Where an installed (Python, langgraph, langchain-core) triple lands, per §4.

    ``str`` mixin for the same reason :class:`~gebra.extraction.warnings.ExtractionWarningCode`
    is one — usable as a report field or a warning-detail value without a conversion step.

    Attributes:
        TESTED: The pair is inside one of the three §1 frozen cells and Python is one of the
            four tested minors (3.10-3.13). The conforming, silent case.
        IN_RANGE_UNTESTED: Every package is inside its declared metadata range
            (``langgraph``/``langchain-core`` ``>=1.0,<2.0``; Python has no declared
            ceiling), but the combination is not a tested cell — an untested pairing, or a
            Python above 3.13. §4: warns :class:`GebraVersionWarning`.
        OUT_OF_RANGE: langgraph or langchain-core is outside ``>=1.0,<2.0`` (a pre-1.0 line,
            or 2.0+), or Python is below the declared 3.10 floor. §4: "loud warning, and
            extraction proceeds best-effort emitting the `unsupported-construct` extraction
            warning carrying the version fact".
    """

    TESTED = "tested"
    IN_RANGE_UNTESTED = "in-range-untested"
    OUT_OF_RANGE = "out-of-range"


@dataclass(frozen=True, slots=True)
class SubstrateVersions:
    """One (Python, langgraph, langchain-core) triple to classify.

    Attributes:
        python: ``sys.version_info``'s ``(major, minor)`` — the check reads no more; a
            patch-level Python difference is never a compatibility axis in §1.
        langgraph: The installed ``langgraph`` distribution version, parsed to a ``(major,
            minor, micro)`` tuple from its leading dotted-numeric run. A prerelease suffix
            (``2.0.0a1``) is discarded, which is the conservative direction: an alpha of the
            next major already carries that major's surface.
        langchain_core: Same parsing, for ``langchain-core``.
        langgraph_raw: The unparsed ``langgraph`` version string, kept for warning detail.
        langchain_core_raw: The unparsed ``langchain-core`` version string.
    """

    python: tuple[int, int]
    langgraph: tuple[int, int, int]
    langchain_core: tuple[int, int, int]
    langgraph_raw: str
    langchain_core_raw: str


@dataclass(frozen=True, slots=True)
class VersionCheck:
    """The memoized result of :func:`check_version_once` — what was seen, and its class."""

    versions: SubstrateVersions
    compat: CompatClass


#: A leading dotted-numeric run: ``major.minor[.micro]``, with anything after (a prerelease
#: or local-version suffix) ignored. ``micro`` defaults to 0 when the string has only two
#: components (langgraph and langchain-core both always publish three, but the parser does
#: not need to assume it).
_LEADING_VERSION: Final = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

#: A version-triple band, half-open: ``[minimum, maximum)``.
_Band = tuple[tuple[int, int, int], tuple[int, int, int]]


@dataclass(frozen=True, slots=True)
class _PairCell:
    """One §1 frozen pair cell, as the half-open version bands it pairs.

    Attributes:
        label: The §1 row this cell is, cited so the mapping stays traceable.
        langgraph: The langgraph band.
        langchain_core: The paired langchain-core band.
    """

    label: str
    langgraph: _Band
    langchain_core: _Band

    def matches(
        self, langgraph: tuple[int, int, int], langchain_core: tuple[int, int, int]
    ) -> bool:
        """Whether ``(langgraph, langchain_core)`` falls inside both of this cell's bands."""
        lg_min, lg_max = self.langgraph
        core_min, core_max = self.langchain_core
        return lg_min <= langgraph < lg_max and core_min <= langchain_core < core_max


#: §1's three frozen pair cells (ratified, walkthrough #1, 2026-07-18), read as version
#: bands per the module docstring's first two embedding choices.
_TESTED_CELLS: Final[tuple[_PairCell, ...]] = (
    _PairCell("langgraph 1.0.x + core 1.0-1.1", ((1, 0, 0), (1, 1, 0)), ((1, 0, 0), (1, 2, 0))),
    _PairCell("langgraph 1.1.x + core 1.2-1.3", ((1, 1, 0), (1, 2, 0)), ((1, 2, 0), (1, 4, 0))),
    _PairCell("langgraph 1.2.x + core >=1.4.7", ((1, 2, 0), (1, 3, 0)), ((1, 4, 7), (2, 0, 0))),
)

#: Python minors the §3 drift matrix runs (VERSION-COMPAT.md §3: "Python (3.10, 3.11, 3.12,
#: 3.13) × the three frozen §1 pair cells").
_TESTED_PYTHON_MINORS: Final[frozenset[tuple[int, int]]] = frozenset(
    {(3, 10), (3, 11), (3, 12), (3, 13)}
)

#: §1's shared installability envelope for both packages: ``>=1.0.0,<2.0.0``.
_INSTALL_FLOOR: Final = (1, 0, 0)
_INSTALL_CEILING: Final = (2, 0, 0)  # exclusive

#: §1's declared Python floor. No declared ceiling — a newer Python is in-range-untested,
#: never out-of-range (§4's own example: "a Python above the tested 3.13 ceiling (e.g.
#: 3.14)").
_PYTHON_FLOOR: Final = (3, 10)


def _parse_leading_version(raw: str) -> tuple[int, int, int]:
    """``raw``'s leading ``major.minor[.micro]`` run, as a comparable tuple.

    Raises:
        ValueError: if ``raw`` has no leading dotted-numeric run at all — not reachable for
            a well-formed PyPI distribution version, but named rather than left to a
            confusing ``TypeError`` from ``None.groups()``.
    """
    match = _LEADING_VERSION.match(raw)
    if match is None:
        raise ValueError(f"{raw!r} has no leading dotted-numeric version to parse")
    major, minor, micro = match.groups()
    return (int(major), int(minor), int(micro) if micro is not None else 0)


def read_installed_versions() -> SubstrateVersions:
    """The live (Python, langgraph, langchain-core) triple — distribution metadata only.

    Reads ``importlib.metadata.version()`` for both packages, never ``import``\\ ing
    either: gebra depends on both, so their distribution metadata is always present, and
    reading it costs nothing extraction-adjacent (WA-07 — this is a metadata read, not an
    import of the substrate).
    """
    langgraph_raw = metadata.version("langgraph")
    langchain_core_raw = metadata.version("langchain-core")
    return SubstrateVersions(
        python=(sys.version_info.major, sys.version_info.minor),
        langgraph=_parse_leading_version(langgraph_raw),
        langchain_core=_parse_leading_version(langchain_core_raw),
        langgraph_raw=langgraph_raw,
        langchain_core_raw=langchain_core_raw,
    )


def classify_substrate(versions: SubstrateVersions) -> CompatClass:
    """Where ``versions`` lands against the §1 ranges and the §3 tested matrix.

    Out-of-range is decided per package/interpreter against the shared ``>=1.0,<2.0``
    envelope (Python against its declared 3.10 floor only); only once every axis is
    in-range does the check look for a matching tested cell, per §1's "the pair matrix, not
    independent ranges" — a langgraph in one cell's band paired with a langchain-core from a
    *different* cell's band is an untested pairing, not a tested one, even though both
    packages are individually within the overall envelope.
    """
    langgraph_in_range = _INSTALL_FLOOR <= versions.langgraph < _INSTALL_CEILING
    core_in_range = _INSTALL_FLOOR <= versions.langchain_core < _INSTALL_CEILING
    python_in_range = versions.python >= _PYTHON_FLOOR
    if not (langgraph_in_range and core_in_range and python_in_range):
        return CompatClass.OUT_OF_RANGE

    tested_pair = any(
        cell.matches(versions.langgraph, versions.langchain_core) for cell in _TESTED_CELLS
    )
    tested_python = versions.python in _TESTED_PYTHON_MINORS
    if tested_pair and tested_python:
        return CompatClass.TESTED
    return CompatClass.IN_RANGE_UNTESTED


def _in_range_untested_message(versions: SubstrateVersions) -> str:
    return (
        "gebra has not been tested against this exact substrate pairing — python "
        f"{versions.python[0]}.{versions.python[1]}, langgraph {versions.langgraph_raw}, "
        f"langchain-core {versions.langchain_core_raw} — though every one of them is "
        "within gebra's declared version ranges; extraction is unverified against this "
        "pair (VERSION-COMPAT.md §4)"
    )


def out_of_range_warning(versions: SubstrateVersions) -> ExtractionWarning:
    """The ``unsupported-construct`` extraction warning an out-of-range install carries (§4).

    Carries INTROSPECTION-SPEC §8's four ``unsupported-construct`` facts — ``construct``,
    ``location``, ``why``, ``ir_partial`` — the same keys every other emitter in the tree
    uses (:mod:`gebra.extraction.builder`, :mod:`.compiled`, :mod:`.lcel`, :mod:`.state`,
    :mod:`.digests`), plus the version facts themselves. ``location`` is the empty mapping:
    this is a fact about the installed substrate, not about a node, an edge or a state key,
    and none of those is the honest answer to "where". ``ir_partial`` is ``False``: an
    out-of-range substrate does not, by itself, drop anything from *this* IR — it says the
    result is unverified, which is a claim about confidence, not about completeness.

    Built fresh on every call so it rides *every* envelope this process produces while the
    install stays out of range — a per-extraction fact, unlike :class:`GebraVersionWarning`,
    which fires at most once per process. See :func:`check_version_once`'s docstring for why
    the two are handled differently.
    """
    why = "installed substrate is outside the declared >=1.0,<2.0 range"
    return ExtractionWarning(
        code=ExtractionWarningCode.UNSUPPORTED_CONSTRUCT,
        message=(
            "the installed substrate is outside gebra's supported version range "
            f"(langgraph {versions.langgraph_raw}, langchain-core "
            f"{versions.langchain_core_raw}, python {versions.python[0]}."
            f"{versions.python[1]}); extraction proceeded best-effort and is unverified "
            "(VERSION-COMPAT.md §1, §4)"
        ),
        detail={
            "construct": "substrate-version",
            "location": {},
            "why": why,
            "ir_partial": False,
            "python": f"{versions.python[0]}.{versions.python[1]}",
            "langgraph": versions.langgraph_raw,
            "langchain_core": versions.langchain_core_raw,
        },
    )


def _compute_version_check() -> VersionCheck:
    """Read the live substrate and classify it — the part that must run exactly once."""
    versions = read_installed_versions()
    return VersionCheck(versions=versions, compat=classify_substrate(versions))


#: The memoized classification. Resolved now, at this module's own import, rather than on
#: the first call below — see the module docstring's "one import-time side effect" section.
#: ``None`` only if that eager resolution itself failed (never observed against a real
#: install, since gebra depends on both distributions), in which case
#: :func:`check_version_once` resolves it lazily on its own first call instead — still never
#: raising ``import gebra`` on version grounds either way.
_cached: VersionCheck | None = None
with contextlib.suppress(Exception):
    _cached = _compute_version_check()

#: Whether :class:`GebraVersionWarning` has already fired this process — the card's
#: "warn-once policy" (``decisions_to_implementer``), tracked separately from ``_cached``
#: so the *classification* can be resolved eagerly above while the *warning* still waits for
#: :func:`check_version_once`'s first call.
_warned = False


def check_version_once() -> VersionCheck:
    """The §4 first-extract check's result — resolved once, warned about at most once.

    The classification itself was very likely already resolved at this module's own import
    (see the module docstring); this only recomputes it if that resolution failed. Either
    way, this is what makes the check "the first ``extract()`` call"'s: nothing outside this
    module observes the classification until something calls this function, and the only
    caller in the shipped extraction path is :func:`gebra.extraction.dispatch.extract`. The
    :class:`GebraVersionWarning` for an in-range-but-untested install is gated on ``_warned``
    rather than reissued: it fires exactly once no matter how many times ``extract()`` runs
    in this process, which is this card's own warn-once policy.

    The out-of-range case is different on purpose. The structured, per-extraction fact it
    carries (:func:`out_of_range_warning`) is the caller's
    (:func:`gebra.extraction.dispatch.extract`'s) to attach to *every* envelope produced
    while the install stays out of range: an envelope describes one extraction, and hiding a
    true version fact from extraction #2 because extraction #1 already reported it would
    make that envelope less honest, not less noisy. Only the Python-level warning is
    warn-once; what a caller does with :attr:`VersionCheck.compat` is not.
    """
    global _cached, _warned
    if _cached is None:
        _cached = _compute_version_check()
    if _cached.compat is CompatClass.IN_RANGE_UNTESTED and not _warned:
        warnings.warn(
            _in_range_untested_message(_cached.versions),
            category=GebraVersionWarning,
            stacklevel=3,
        )
        _warned = True
    return _cached


def reset_version_check_cache() -> None:
    """Clear the memoized classification and the warn-once flag.

    Test-only: lets a test simulate a fresh process after monkeypatching
    :func:`read_installed_versions`, the same shape ``tests/extraction/test_dispatch.py``
    uses ``register_extractor``/``unregister_extractor`` for. Nothing in the shipped
    extraction path calls this.
    """
    global _cached, _warned
    _cached = None
    _warned = False
