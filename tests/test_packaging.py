"""Packaging-configuration tests for the GOV-D1-ruled build system.

The ruling is [PD-005](build-backend ruling, ratified 2026-07-24): the build
backend is hatchling on a ``hatchling>=1.27`` floor, the repo is uv-managed with
``uv.lock`` committed for the default development environment, the setuptools
configuration is gone, and per-cell compatibility pins stay out of the lock (they
belong to the future ``gebra[compat-test]`` extra).

Card REL-02 added the second half: the *page* the distribution carries. PyPI renders
the README and rewrites nothing in it, so a relative link or image that resolves on
GitHub is dead on the project page — the long description is therefore built from
``README.md`` by a pinned metadata hook whose substitutions turn those targets into
absolute URLs. The tests below read that configuration out of ``pyproject.toml`` and
apply it, so the thing under test is the configuration the build reads rather than a
description of it.

These tests read files and parse TOML only. Nothing here builds, installs,
imports a workflow, executes a node, calls an LLM, or opens a socket (WA-07).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.docs.test_readme import _LINK_RE

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
LOCKFILE = REPO_ROOT / "uv.lock"
README = REPO_ROOT / "README.md"

#: The build requirements, in order, each pinned to one version. GOV-13's rule applies to
#: every tool an isolated build resolves fresh and that decides what the published artifact
#: says: the backend (which emits the Metadata-Version twine validates) and the metadata hook
#: (which decides the text of the long description PyPI renders).
BUILD_REQUIREMENTS = ["hatchling==1.27.0", "hatch-fancy-pypi-readme==24.1.0"]

#: A requirement pinned to exactly one version. A floor (``>=``), a compatible release
#: (``~=``), a range or a bare name all fail it — see
#: :func:`test_an_unpinned_build_requirement_is_refused` for that half of the claim.
_PINNED_REQUIREMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][^,;<>=!~\s]*")

#: Where the rewritten targets point. A page is served from the raw host; a file or a
#: directory a reader opens is served from the blob view, which redirects to the tree view
#: when the path is a directory.
REPOSITORY_PAGE = "https://github.com/Gebra-Tech/gebra"
BLOB_PREFIX = f"{REPOSITORY_PAGE}/blob/main/"
RAW_PREFIX = "https://raw.githubusercontent.com/Gebra-Tech/gebra/main/"

#: Where the documentation site is served (REL-03). `mkdocs.yml` declares it as `site_url`
#: and `tests/docs/test_readme.py` holds the two to one address; here it is what the
#: project's own metadata sends a reader on PyPI to.
DOCUMENTATION_SITE = "https://gebra-tech.github.io/gebra/"

#: The schemes a target may already carry; the substitutions leave these alone.
ABSOLUTE_SCHEMES = ("https://", "http://", "mailto:")

pytestmark = pytest.mark.skipif(
    not PYPROJECT.is_file(),
    reason="packaging tests describe the source tree; no pyproject.toml beside tests/",
)


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    return _load(PYPROJECT)


@pytest.fixture(scope="module")
def lockfile() -> dict[str, Any]:
    if not LOCKFILE.is_file():
        pytest.fail("uv.lock is missing; PD-005 item 3 requires it committed at the repo root")
    return _load(LOCKFILE)


def test_build_backend_is_hatchling(pyproject: dict[str, Any]) -> None:
    """PD-005 item 1's backend, pinned exactly under GOV-08's freeze doctrine.

    1.27 remains the PEP 639 floor (``license = "Apache-2.0"`` + ``license-files``
    need it), but the requirement is now ``==``, not ``>=``: isolated builds resolve
    the backend fresh, and a hatchling release bumping Metadata-Version ahead of the
    twine validators turned GOV-03's release gate red on its first run (fresh
    hatchling emitted 2.5; twine 6.1.0 and 6.2.0 both reject it). Reproducible
    release builds pin the backend; bumps are deliberate, paired with the twine pin.

    ``hatch-fancy-pypi-readme`` (REL-02) joins it under the same rule: it is a metadata
    *hook*, not a second backend — ``build-backend`` stays hatchling's — but it is
    resolved fresh by every isolated build and it decides the text of the long
    description, so a floating resolution could move the published page under a release
    with no commit saying so. Two requirements, both ``==``, and nothing else.
    """
    build_system = pyproject["build-system"]
    assert build_system["build-backend"] == "hatchling.build"
    assert build_system["requires"] == BUILD_REQUIREMENTS
    unpinned = [
        requirement
        for requirement in build_system["requires"]
        if not _PINNED_REQUIREMENT.fullmatch(requirement)
    ]
    assert unpinned == [], f"a build requirement is not pinned to one version: {unpinned}"
    assert pyproject["project"]["license"] == "Apache-2.0"
    assert pyproject["project"]["license-files"] == ["LICENSE", "NOTICE"]


@pytest.mark.parametrize(
    "requirement",
    ["hatchling", "hatchling>=1.27.0", "hatchling~=1.27.0", "hatchling>=1.27,<2", "hatchling==*"],
)
def test_an_unpinned_build_requirement_is_refused(requirement: str) -> None:
    """The other half of the pin: the check above refuses what GOV-13 was caused by.

    ``hatchling>=1.27`` is the spelling the release gate went red on — the assertion
    that rejects it has to be shown rejecting it, or "pinned exactly" is a claim about
    one literal string rather than about a rule.
    """
    assert _PINNED_REQUIREMENT.fullmatch(requirement) is None


def test_no_setuptools_configuration_survives(pyproject: dict[str, Any]) -> None:
    """PD-005 item 2: the ``[tool.setuptools.*]`` tables and their era are gone."""
    assert "setuptools" not in pyproject.get("tool", {})
    for legacy in ("setup.py", "setup.cfg", "MANIFEST.in"):
        assert not (REPO_ROOT / legacy).exists(), f"setuptools-era file survives: {legacy}"


def test_no_egg_info_artifacts_in_the_tree() -> None:
    """PD-005 item 2, egg-info hygiene: no in-tree ``*.egg-info`` build artifact.

    Hatchling never produces one; a reappearance means something built through
    setuptools again.
    """
    candidates = [*REPO_ROOT.glob("*.egg-info"), *REPO_ROOT.glob("*/*.egg-info")]
    strays = sorted(
        str(path.relative_to(REPO_ROOT)) for path in candidates if ".venv" not in path.parts
    )
    assert strays == []


def test_wheel_packages_the_src_layout_and_the_typing_marker(pyproject: dict[str, Any]) -> None:
    """The wheel carries ``gebra/`` from ``src/gebra/``, ``py.typed`` included.

    Hatchling ships every file under a packaged directory, so the marker needs no
    separate package-data declaration — but it does need to exist.
    """
    wheel_target = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel_target["packages"] == ["src/gebra"]
    assert (REPO_ROOT / "src" / "gebra" / "py.typed").is_file()


# ── The long description the index renders (REL-02) ──────────────────────────────────────


def _readme_hook(pyproject: dict[str, Any]) -> dict[str, Any]:
    hook: dict[str, Any] = pyproject["tool"]["hatch"]["metadata"]["hooks"]["fancy-pypi-readme"]
    return hook


def _build_long_description(pyproject: dict[str, Any]) -> str:
    """The long description the distribution carries, built the way the hook builds it.

    ``hatch_fancy_pypi_readme`` concatenates the fragments and applies each substitution in
    configuration order with ``re.sub``, compiled with no flags unless ``ignore-case`` is set
    — so this is the same text, not an approximation of it. The configuration is read out of
    ``pyproject.toml``: a copy here would be a second source of truth, and the point of the
    check is that the file the build reads is the file under test.
    """
    hook = _readme_hook(pyproject)
    text = "".join(
        (REPO_ROOT / fragment["path"]).read_text(encoding="utf-8") for fragment in hook["fragments"]
    )
    for substitution in hook["substitutions"]:
        assert not substitution.get("ignore-case", False), (
            "an `ignore-case` substitution compiles with re.IGNORECASE; this rebuild does not"
        )
        text = re.sub(substitution["pattern"], substitution["replacement"], text)
    return text


def _repository_path(target: str) -> str:
    """The in-tree path a rewritten target names, fragment kept."""
    for prefix in (BLOB_PREFIX, RAW_PREFIX):
        if target.startswith(prefix):
            return target[len(prefix) :]
    raise AssertionError(f"{target!r} is not a rewritten repository target")


def _relative_targets(text: str) -> list[str]:
    return [
        match.group("target")
        for match in _LINK_RE.finditer(text)
        if not match.group("target").startswith(ABSOLUTE_SCHEMES)
    ]


def test_the_long_description_is_built_from_the_readme_by_the_metadata_hook(
    pyproject: dict[str, Any],
) -> None:
    """The declaration: dynamic readme, one fragment, three substitutions in the ruled order.

    ``dynamic = ["readme"]`` is what hands the field to the hook; a static ``readme =`` line
    beside it is an error the backend raises, and without the hook the field would simply be
    missing. The substitution order is load-bearing and is asserted as behaviour rather than
    as three literal strings: an image is a link too, so rewriting images first is what lets
    the link rule stay one expression.
    """
    project = pyproject["project"]
    assert project["dynamic"] == ["readme"]
    assert "readme" not in project

    hook = _readme_hook(pyproject)
    assert hook["content-type"] == "text/markdown"
    assert hook["fragments"] == [{"path": "README.md"}]

    assert len(hook["substitutions"]) == 3
    images, links, anchors = hook["substitutions"]
    assert re.sub(images["pattern"], images["replacement"], "![logo](docs/x.png)") == (
        f"![logo]({RAW_PREFIX}docs/x.png)"
    )
    assert re.sub(images["pattern"], images["replacement"], "[a](docs/x.md)") == "[a](docs/x.md)"
    assert re.sub(links["pattern"], links["replacement"], "[a](docs/x.md)") == (
        f"[a]({BLOB_PREFIX}docs/x.md)"
    )
    assert re.sub(links["pattern"], links["replacement"], "[a](https://x.test/)") == (
        "[a](https://x.test/)"
    )
    assert re.sub(anchors["pattern"], anchors["replacement"], "[a](#install)") == (
        f"[a]({REPOSITORY_PAGE}#install)"
    )
    # Order: run the link rule on an un-rewritten image and it lands on the blob view, which
    # serves an HTML page rather than a picture. Images first is why that cannot happen.
    assert re.sub(links["pattern"], links["replacement"], "![logo](docs/x.png)") == (
        f"![logo]({BLOB_PREFIX}docs/x.png)"
    )


def test_the_long_description_carries_no_relative_link(pyproject: dict[str, Any]) -> None:
    """REL-02's objective, checked on the built text: the page stands on its own.

    PyPI serves the long description as it is given and rewrites nothing in it
    (pypa/readme_renderer#163, open), so every relative target on the source page would be a
    dead link on the project page and the logo would not render at all. After the
    substitutions: no target is relative, no bare ``#anchor`` survives, every rewritten path
    is a path that exists in this tree, and the logo resolves to the raw host.
    """
    text = _build_long_description(pyproject)
    targets = [match.group("target") for match in _LINK_RE.finditer(text)]

    assert targets, "the built page links nothing — the fragment or the grammar moved"
    assert _relative_targets(text) == []
    assert "](#" not in text

    rewritten = [target for target in targets if target.startswith((BLOB_PREFIX, RAW_PREFIX))]
    assert rewritten, "nothing was rewritten; the substitutions no longer reach this page"
    missing = [
        target
        for target in rewritten
        if not (REPO_ROOT / _repository_path(target).split("#", 1)[0]).exists()
    ]
    assert missing == [], f"rewritten to a path that is not in the tree: {missing}"

    assert f"![gebra]({RAW_PREFIX}docs/assets/gebra-logo.png)" in text


def test_the_substitutions_rewrite_exactly_the_links_the_readme_page_test_counts(
    pyproject: dict[str, Any],
) -> None:
    """The page's own link check and the rewrite agree about what a link is.

    ``tests/docs/test_readme.py::test_every_relative_link_resolves`` is what keeps the
    README's relative targets real, and it reads them with ``_LINK_RE`` — imported here
    rather than restated, so the two cannot drift. If the rewrite saw fewer links than that
    check does, a target could be declared resolvable there and left relative here: dead on
    the index page, with nothing red. The two lists are equal, in order.
    """
    relative = _relative_targets(README.read_text(encoding="utf-8"))
    rewritten = [
        _repository_path(match.group("target"))
        for match in _LINK_RE.finditer(_build_long_description(pyproject))
        if match.group("target").startswith((BLOB_PREFIX, RAW_PREFIX))
    ]

    assert relative, "the README has no relative link; the grammar moved"
    assert rewritten == relative


def test_every_anchor_into_the_readmes_own_sections_lands_on_the_repository_page(
    pyproject: dict[str, Any],
) -> None:
    """A bare ``#anchor`` resolves to a section of the *page it is on*.

    On PyPI that page is the project page, whose headings are not the README's, so the
    anchors are sent to the repository page instead — where the heading slugs GitHub derives
    are the ones ``tests/docs/test_readme.py::test_every_anchor_link_names_a_heading``
    already holds the README to.
    """
    anchors = re.findall(r"\]\(#([^)]+)\)", README.read_text(encoding="utf-8"))
    text = _build_long_description(pyproject)

    assert anchors, "the page links no section of its own"
    for anchor in anchors:
        assert f"]({REPOSITORY_PAGE}#{anchor})" in text


def test_the_sdist_carries_the_documents_the_readme_links(pyproject: dict[str, Any]) -> None:
    """The fragment and the agreement ship in the source distribution.

    Two reasons, and only one of them is about a reader. A wheel built *from* the sdist —
    which is what ``uv build``'s second leg does, and what an index-side build of the sdist
    does — runs the metadata hook there, so a missing ``README.md`` is a failed build rather
    than a plain long description. A static ``readme =`` was carried into the sdist by
    hatchling on its own; a ``dynamic`` one is not, so the explicit include list has to name
    it. ``CLA.md`` is the second: both the README and CONTRIBUTING.md link the agreement a
    contribution needs signed first, and an sdist reader should find it beside them.
    ``SECURITY.md`` joined them at REL-04, linked from the README on the same reasoning.
    ``LICENSE`` and ``NOTICE`` ride in through ``license-files`` (asserted in
    :func:`test_build_backend_is_hatchling`).
    """
    include = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]

    for fragment in _readme_hook(pyproject)["fragments"]:
        assert f"/{fragment['path']}" in include, (
            f"the long-description fragment {fragment['path']} is not in the sdist"
        )
    for document in ("/CLA.md", "/CONTRIBUTING.md", "/CHANGELOG.md", "/SECURITY.md"):
        assert document in include
        assert (REPO_ROOT / document.lstrip("/")).is_file(), document


def test_the_project_metadata_names_its_tracker_its_audience_and_its_maturity(
    pyproject: dict[str, Any],
) -> None:
    """What the index page says about the project beside the README (REL-02).

    ``Issues`` is the sidebar link a reader reaches for when something is wrong.
    ``Development Status`` is ``3 - Alpha``: the public API surfaces are frozen documents,
    the tested matrix is twelve blocking CI cells and the package is published — more than
    ``2 - Pre-Alpha`` says, and less than the stable API a ``4 - Beta`` would imply. The
    ``Framework`` and ``Topic`` lines are what a reader browsing PyPI by subject looks
    under. ``Documentation`` joined them at REL-03 and not before: it was absent while the
    site was built and unpublished, because a project URL naming a page that 404s is worse
    than no URL. The set is asserted, not just its members, so a fifth link cannot arrive
    without a reader of this test deciding it should.
    """
    project = pyproject["project"]

    assert project["urls"]["Issues"] == f"{REPOSITORY_PAGE}/issues"
    assert project["urls"]["Documentation"] == DOCUMENTATION_SITE
    assert set(project["urls"]) == {
        "Homepage",
        "Repository",
        "Documentation",
        "Issues",
        "Changelog",
    }

    classifiers = project["classifiers"]
    assert [line for line in classifiers if line.startswith("Development Status ::")] == [
        "Development Status :: 3 - Alpha"
    ]
    assert "Framework :: Pytest" in classifiers
    assert {
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Libraries :: Python Modules",
    } <= set(classifiers)
    # Kept sorted: the list is grouped by trove namespace and read by eye at every release.
    assert classifiers == sorted(classifiers)


def test_the_pytest_plugin_is_declared_as_a_pytest11_entry_point(
    pyproject: dict[str, Any],
) -> None:
    """D-10 In-Scope 2, card TE-06: the plugin ships in the distribution's metadata.

    The source-side half of the claim — the declaration exists and names a module that is
    actually in the wheel. The installed-metadata half is
    ``tests/plugin/test_plugin.py::test_the_plugin_loads_from_its_entry_point``, because a
    declaration that never made it into a dist-info does nothing.
    """
    entry_points = pyproject["project"]["entry-points"]["pytest11"]
    assert entry_points == {"gebra": "gebra.pytest_plugin"}
    assert (REPO_ROOT / "src" / "gebra" / "pytest_plugin.py").is_file()


def test_lockfile_matches_the_declared_python_floor(
    pyproject: dict[str, Any], lockfile: dict[str, Any]
) -> None:
    """PD-005 item 3: the committed lock locks *this* project's environment."""
    assert lockfile["requires-python"] == pyproject["project"]["requires-python"]


def test_lockfile_covers_the_declared_dependency_set(
    pyproject: dict[str, Any], lockfile: dict[str, Any]
) -> None:
    """Every declared runtime and dev distribution resolves to a locked package."""
    locked = {package["name"] for package in lockfile["package"]}
    declared = [
        *pyproject["project"]["dependencies"],
        *pyproject["project"]["optional-dependencies"]["dev"],
    ]
    missing = sorted(
        {_distribution_name(requirement) for requirement in declared} - locked - {"gebra"}
    )
    assert missing == [], f"declared but unlocked: {missing} — refresh uv.lock"


def test_lockfile_carries_no_matrix_pins(
    pyproject: dict[str, Any], lockfile: dict[str, Any]
) -> None:
    """PD-005 item 4 as amended at PD-049: the lock never decides what a cell tests.

    The compat extras (SOW §4; values recorded by GOV-D3, installed per cell by GOV-04)
    pin mutually exclusive substrates, and ``uv lock`` resolves every extra of a project —
    the original letter ("pins never enter the lock") was unsatisfiable alongside a
    resolvable lock, which the first real CI run surfaced (PD-049, 2026-08-13; filed as PD-046, renumbered). The
    surviving invariants, asserted here: every compat extra is declared in one
    ``[tool.uv] conflicts`` set (so the lock records them only as conflicting
    alternatives), and the DEV line's substrate resolution is exactly the ruled dev pins —
    the cells still install from ``pyproject.toml`` via pip, never from the lock.
    """
    declared = {
        extra
        for extra in pyproject["project"]["optional-dependencies"]
        if extra.startswith("compat")
    }
    assert declared, "the compatibility extras are gone; SOW §4 requires them"
    conflict_sets = pyproject.get("tool", {}).get("uv", {}).get("conflicts", [])
    conflicted = {
        member["extra"]
        for conflict_set in conflict_sets
        for member in conflict_set
        if "extra" in member
    }
    assert declared <= conflicted, (
        "every compat extra must be declared conflicting (PD-049); missing: "
        f"{sorted(declared - conflicted)}"
    )
    # The dev line is untouched by the cells: the newest-pair substrate (the ruled dev
    # line, == cell 3's pins per PD-030 §C3) is present in the lock, and the older cells'
    # substrate versions appear only as conflict-split alternatives, never displacing it.
    expected_dev = {"langgraph": "1.2.10", "langchain-core": "1.5.3"}
    for name, version in expected_dev.items():
        found = {package["version"] for package in lockfile["package"] if package["name"] == name}
        assert version in found, f"dev-line {name}=={version} missing from the lock: {found}"


def _locked_project_extras(lockfile: dict[str, Any]) -> set[str]:
    for package in lockfile["package"]:
        if package["name"] == "gebra":
            return set(package.get("optional-dependencies", {}))
    pytest.fail("uv.lock does not contain the gebra project package")


def _distribution_name(requirement: str) -> str:
    """Normalize a PEP 508 requirement string to its PEP 503 distribution name."""
    name = requirement.split(";", 1)[0]
    for separator in ("[", "=", "<", ">", "!", "~", " "):
        name = name.split(separator, 1)[0]
    return name.strip().lower().replace("_", "-").replace(".", "-")
