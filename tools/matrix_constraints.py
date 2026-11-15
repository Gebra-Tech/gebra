"""Generate or verify the matrix constraints file — the freeze-time pin lock (GOV-08).

The 12 frozen matrix cells, the DoD job, the ``pip-editable`` job and the ``docs`` job all
install with pip from floors (``pip install -e ".[dev,...]"``), so before the F2 freeze
their non-substrate resolution was whatever the index served that day. Two ecosystem-drift
events during G6 proved the exposure (a hypothesis profile change → TE-16; typer 0.27.2 →
CLI-10), and the G6 sign-off routed its closure here: at the freeze, every pip-installing
CI job resolves against ``tools/matrix-constraints.txt`` (``pip install -c``), a
constraints file derived from the committed ``uv.lock`` — the same resolution the locked
jobs already run. Two deliberate exceptions stay fresh: the ``--pre`` cell's substrate
resolve step (that cell exists to see today's index, VERSION-COMPAT §3) and the build
job's clean-venv wheel smoke (a user-shaped install is its point — the release
workflow's own posture).

What the file carries, and what it deliberately leaves out:

* **One ``name==version`` line per locked distribution** that resolves to a single version
  for every environment — the dev toolchain and its transitives.
* **Marker-scoped lines** for a distribution the lock resolves per Python version (for
  example networkx below/at the 3.11 boundary): one line per locked version, scoped by the
  lock's own resolution markers. A constraints line never *installs* anything, so a line
  whose marker does not match the running interpreter is inert.
* **No line at all for the substrate family** — every distribution the ``compat-cell-N``
  extras pin. The three cells pin those to mutually exclusive versions by design
  (VERSION-COMPAT §1/§3); their single source of truth is the extras, and a constraint
  would either duplicate or contradict them. A family member is still constrained when
  every extra that pins it agrees on one version and the lock resolved exactly that
  version: the constraint then also covers the jobs that install no cell extra (pydantic
  and langchain-protocol were, until cell 3's GOV-16 extension pinned them apart). A
  distribution whose resolution the lock makes cell-dependent (uv conflict markers —
  packaging today) is likewise left to the cell's own resolution, and every such
  exclusion is listed by name in the generated header.
* **The one marker a compat extra may carry is a Python-version bound**
  (``python_version >= '3.11'``), for a cell that pins a family member per interpreter —
  cell 3's langchain-core since GOV-16 (PD-078), where the newest core inside the cell's
  pins declares a ``Requires-Python`` that excludes one of the cell's Pythons.
  :func:`split_requirement` reads such a pin's version without its marker and
  :func:`cell_pins` resolves an extra for one Python; any other marker is refused (exit 2)
  rather than guessed at.

``--check`` regenerates in memory and compares against the committed file (CI-testable:
``tests/test_matrix_constraints.py`` runs it in-process in every cell, so a ``uv.lock``
refresh without its constraints refresh is a red test, not a silent skew). ``--write``
rewrites the file; run it in the same commit as any ``uv.lock`` change. Exit codes:
0 = clean, 1 = the committed file is stale or missing, 2 = the inputs are inconsistent
(unparsable lock, or the lock and the compat extras disagree on an agreed family pin) —
never a silent pass.

WA-07: this tool reads two TOML files and writes one text file. It installs nothing,
executes no workflow node, calls no model, and opens no network connection.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = REPO_ROOT / "uv.lock"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CONSTRAINTS = REPO_ROOT / "tools" / "matrix-constraints.txt"

#: The reason strings the generated header carries per excluded distribution.
REASON_PROJECT = "the project itself, installed editable by every job"
REASON_FAMILY = "substrate family - pinned per cell by the compat-cell extras"
REASON_CELL_DEPENDENT = "cell-dependent resolution (uv conflict markers) - left to the cell"
REASON_AMBIGUOUS = "multiple locked versions with no per-environment markers - left unpinned"

HEADER = """\
# tools/matrix-constraints.txt - the freeze-time pin lock (GOV-08, F2; VERSION-COMPAT S4).
#
# GENERATED from the committed uv.lock by tools/matrix_constraints.py - do not edit by
# hand. Regenerate with `python tools/matrix_constraints.py --write` in the same commit as
# any uv.lock refresh; `--check` (run by tests/test_matrix_constraints.py in every CI
# cell) fails when the two files skew.
#
# Every pip-installing CI job passes this file to `pip install -c`, so a matrix cell,
# the DoD job, the docs job and the pip-editable job resolve their dependencies to the
# versions the locked jobs run, instead of to whatever the index serves that day (the
# build job's clean-venv wheel smoke and the --pre cell's substrate resolve deliberately
# stay fresh). Distributions the cells pin to *different* versions are never constrained
# here - the compat-cell extras are their single source of truth; a family member
# appears below only when every extra that pins it agrees on one version and the lock
# resolved exactly that version. Anything else the lock resolves per cell is left to the
# cell and named below. A constraints line binds only when the named distribution is
# selected; it never installs anything by itself.
#
# Excluded from constraint, with reasons:
"""


class MatrixConstraintsError(RuntimeError):
    """An inconsistency this tool refuses to paper over (exit 2, never a silent pass)."""


def canonical_name(name: str) -> str:
    """PEP 503 normalization, so pyproject and uv.lock spellings compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


#: The one environment marker a compat extra may carry: a bound on the Python minor. It lets
#: a cell pin a family member per interpreter where the newest release inside the cell's pins
#: declares a ``Requires-Python`` that excludes one of the cell's Pythons (cell 3's
#: langchain-core since GOV-16, PD-078). Whitespace around the operator is free; the quoted
#: bound is ``major.minor``, as pip compares ``python_version``.
_PYTHON_MARKER = re.compile(r"""python_version\s*(<=|>=|==|!=|<|>)\s*(['"])(\d+)\.(\d+)\2""")

#: What a pin's version may not contain: anything that makes it a range rather than a pin.
_RANGE_CHARACTERS = frozenset("<>!=~,*")


def split_requirement(requirement: str) -> tuple[str, str, str | None]:
    """A compat-extra line, ``name==version[; python_version <op> 'X.Y']``, as its parts.

    Returns ``(name, version, marker)``: the PEP 503-normalized name, the exact version, and
    the marker text — ``None`` for a pin every Python installs.

    Raises:
        MatrixConstraintsError: the line is not an exact pin, or it carries any marker other
            than one Python-version bound.
    """
    spec, separator, marker = requirement.partition(";")
    name, equals, version = spec.partition("==")
    version = version.strip()
    if not equals or not name.strip() or not version or _RANGE_CHARACTERS & set(version):
        raise MatrixConstraintsError(f"a compat extra carries a non-exact pin: {requirement!r}")
    if not separator:
        return canonical_name(name.strip()), version, None
    marker = marker.strip()
    if _PYTHON_MARKER.fullmatch(marker) is None:
        raise MatrixConstraintsError(
            f"a compat extra carries a marker other than a python_version bound: {requirement!r}"
        )
    return canonical_name(name.strip()), version, marker


def marker_admits(marker: str | None, python: tuple[int, int]) -> bool:
    """Whether a pin carrying ``marker`` installs on the Python minor ``python``."""
    if marker is None:
        return True
    matched = _PYTHON_MARKER.fullmatch(marker)
    if matched is None:
        raise MatrixConstraintsError(f"not a python_version bound: {marker!r}")
    operator, _, major, minor = matched.groups()
    bound = (int(major), int(minor))
    verdicts = {
        "<": python < bound,
        "<=": python <= bound,
        ">": python > bound,
        ">=": python >= bound,
        "==": python == bound,
        "!=": python != bound,
    }
    return verdicts[operator]


def cell_pins(requirements: Sequence[str], python: tuple[int, int]) -> dict[str, str]:
    """The exact pins one compat extra installs on the Python minor ``python``, by name.

    Raises:
        MatrixConstraintsError: a line is not a pin :func:`split_requirement` reads, or two
            pins of one distribution apply to the same Python.
    """
    pins: dict[str, str] = {}
    for requirement in requirements:
        name, version, marker = split_requirement(str(requirement))
        if not marker_admits(marker, python):
            continue
        if name in pins:
            raise MatrixConstraintsError(
                f"{name} is pinned twice for Python {python[0]}.{python[1]}: "
                f"{pins[name]} and {version}"
            )
        pins[name] = version
    return pins


def compat_extra_pins(pyproject: dict[str, object]) -> dict[str, set[str]]:
    """Every pinned version across the ``compat*`` extras, keyed by name (markers dropped)."""
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise MatrixConstraintsError("pyproject.toml carries no [project] table")
    extras = project.get("optional-dependencies")
    if not isinstance(extras, dict):
        raise MatrixConstraintsError("pyproject.toml carries no optional dependencies")
    pins: dict[str, set[str]] = {}
    for extra_name, requirements in extras.items():
        if not str(extra_name).startswith("compat"):
            continue
        for requirement in requirements:
            try:
                name, version, _ = split_requirement(str(requirement))
            except MatrixConstraintsError as error:
                raise MatrixConstraintsError(f"extra {extra_name!r}: {error}") from None
            pins.setdefault(name, set()).add(version)
    if not pins:
        raise MatrixConstraintsError("no compat* extra found - the substrate family is gone?")
    return pins


def locked_packages(lock: dict[str, object]) -> dict[str, list[tuple[str, list[str]]]]:
    """The lock's ``[[package]]`` entries as name -> [(version, resolution-markers)]."""
    entries = lock.get("package")
    if not isinstance(entries, list) or not entries:
        raise MatrixConstraintsError("uv.lock carries no [[package]] entries")
    packages: dict[str, list[tuple[str, list[str]]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise MatrixConstraintsError("uv.lock [[package]] entry is not a table")
        name = canonical_name(str(entry["name"]))
        version = str(entry["version"])
        markers = [str(marker) for marker in entry.get("resolution-markers", [])]
        packages.setdefault(name, []).append((version, markers))
    return packages


def _python_only(markers: list[str]) -> bool:
    """Whether every marker is an environment fact pip can evaluate at install time.

    The lock's conflict algebra (``extra == 'extra-5-gebra-compat-...'``) is uv-internal:
    pip evaluates ``extra`` against nothing during a constraints match, so such a marker
    cannot be copied into the file — the distribution is excluded instead.
    """
    return bool(markers) and all("extra" not in marker for marker in markers)


def render(lock: dict[str, object], pyproject: dict[str, object]) -> str:
    """The full constraints file content for the given lock + pyproject."""
    family = compat_extra_pins(pyproject)
    packages = locked_packages(lock)

    lines: list[str] = []
    excluded: list[tuple[str, str]] = []
    for name in sorted(packages):
        entries = sorted(packages[name])
        if name == "gebra":
            excluded.append((name, REASON_PROJECT))
            continue
        if name in family:
            agreed = family[name]
            if len(agreed) == 1 and len(entries) == 1 and entries[0][0] == next(iter(agreed)):
                lines.append(f"{name}=={entries[0][0]}")
            elif len(agreed) == 1 and len(entries) == 1:
                raise MatrixConstraintsError(
                    f"{name}: the compat extras agree on =={next(iter(agreed))} but the "
                    f"lock resolved {entries[0][0]} - reconcile before freezing"
                )
            else:
                excluded.append((name, REASON_FAMILY))
            continue
        if len(entries) == 1:
            lines.append(f"{name}=={entries[0][0]}")
            continue
        fragments = [marker for _, markers in entries for marker in markers]
        partitioned = len(fragments) == len(set(fragments))
        if all(_python_only(markers) for _, markers in entries) and partitioned:
            for version, markers in entries:
                joined = " or ".join(f"({marker})" for marker in markers)
                lines.append(f"{name}=={version} ; {joined}")
        elif fragments and not partitioned:
            # The same python-marker fragment serving two versions means python is not
            # the discriminator - the lock split this distribution on its conflict
            # dimension (packaging today), and two overlapping constraints would refuse
            # every resolution instead of locking one.
            excluded.append((name, REASON_CELL_DEPENDENT))
        elif any("extra" in marker for marker in fragments):
            excluded.append((name, REASON_CELL_DEPENDENT))
        else:
            excluded.append((name, REASON_AMBIGUOUS))

    header = HEADER + "".join(f"#   {name} - {reason}\n" for name, reason in excluded)
    return header + "\n" + "\n".join(lines) + "\n"


def regenerate() -> str:
    """Render from the committed ``uv.lock`` + ``pyproject.toml``."""
    with LOCKFILE.open("rb") as handle:
        lock: dict[str, object] = tomllib.load(handle)
    with PYPROJECT.open("rb") as handle:
        pyproject: dict[str, object] = tomllib.load(handle)
    return render(lock, pyproject)


def _display(path: Path) -> str:
    """The repo-relative spelling when there is one; the absolute path otherwise."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def check() -> int:
    """0 iff the committed file matches a fresh regeneration byte for byte."""
    fresh = regenerate()
    if not CONSTRAINTS.is_file():
        print(f"STALE {_display(CONSTRAINTS)}: missing - run --write")
        return 1
    committed = CONSTRAINTS.read_text(encoding="utf-8")
    if committed != fresh:
        fresh_lines = fresh.splitlines()
        committed_lines = committed.splitlines()
        divergence = next(
            (
                index
                for index, (have, want) in enumerate(zip(committed_lines, fresh_lines))
                if have != want
            ),
            min(len(committed_lines), len(fresh_lines)),
        )
        print(
            f"STALE {_display(CONSTRAINTS)}: differs from the lock at line "
            f"{divergence + 1} - run `python tools/matrix_constraints.py --write` in the "
            "same commit as the uv.lock change"
        )
        return 1
    constrained = sum(1 for line in committed.splitlines() if line and not line.startswith("#"))
    print(f"OK    {_display(CONSTRAINTS)}: {constrained} constraint(s) match uv.lock")
    return 0


def write() -> int:
    fresh = regenerate()
    CONSTRAINTS.write_text(fresh, encoding="utf-8")
    constrained = sum(1 for line in fresh.splitlines() if line and not line.startswith("#"))
    print(f"WROTE {_display(CONSTRAINTS)}: {constrained} constraint(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the committed file")
    mode.add_argument("--write", action="store_true", help="regenerate the committed file")
    arguments = parser.parse_args(argv)
    try:
        return write() if arguments.write else check()
    except MatrixConstraintsError as error:
        print(f"error: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
