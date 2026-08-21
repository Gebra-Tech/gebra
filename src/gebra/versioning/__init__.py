"""The V.S.F.E version engine — parse a label, compare two labels, bump for a change.

V.S.F.E is the snapshot version scheme of SOW §1: **S bumps on a topology change, F on a
node/contract change, E on a state-schema change**. IR-SPEC §4.1 makes the label the
``version`` field of the snapshot envelope and gives its semantics to brief D-11, whose
In-Scope 2 asks for exactly three things — "parser, comparator, and bump logic: compare the
working IR against the latest snapshot and bump S (topology), F (node/contract), and/or E
(state schema) accordingly"::

    from gebra.versioning import Version, changed_components, next_version

    current = Version.parse("1.4.2.0")

    changed_components(stored_ir, working_ir)     # frozenset({Component.S, Component.E})
    next_version(current, stored_ir, working_ir)  # Version(v=1, s=5, f=2, e=1)
    str(_)                                        # '1.5.2.1'

**The engine stands on its own.** It reads IR models and the IR-SPEC §6 canonical form and
nothing else — no store, no diff engine, no extractor. Handing it two IRs and a label is
the whole interface: :class:`~gebra.versioning.models.Version` for the label,
:func:`~gebra.versioning.classify.changed_components` for the comparison,
:func:`~gebra.versioning.classify.next_version` for both at once, and
:data:`~gebra.versioning.classify.FIELD_COMPONENTS` (with
:func:`~gebra.versioning.classify.components_for_path`) for the S/F/E definition itself, as
a table over the frozen core-IR field vocabulary.

**What a version does and does not tell you.** The counters say which *domain* of a
workflow definition changed since the compared snapshot — its topology, its contracts, its
state schema — and how many times each has changed. They do not say *what* changed: that is
:mod:`gebra.diff`'s job, whose ``workflow_diff`` reports the topology, contract and
state-schema deltas and derives this engine's bump class from them. And they do not say
whether a change is safe or breaking: P-12 ``evolution-safety`` is deferred out of Phase 0
by SOW §8, and nothing here or there classifies one.

**Three rules worth knowing before you read a label.**

* Bumps *do not reset* the components to their right. D-11 In-Scope 2 says S, F "and/or" E
  bump, so the three count changes in their own domain independently.
* The comparison is by canonical content, so a reordered ``nodes`` list, a duplicated
  ``entry`` member, and a state value written in its object form rather than as a bare type
  string are not changes — exactly as they are not ``graph_version`` changes.
* Adding or removing a node moves **S and F** together: the topology gained a vertex and
  the contract set gained a member. So does a rename, which IR-SPEC §5.3 makes a new
  identity rather than a modification.

**V is the caller's.** The frozen package defines S, F and E and says nothing about what V
counts, so this engine never derives a V bump — it carries the component through untouched.

Nothing in this package imports langgraph, opens a socket, or executes anything (WA-07).
Its inputs are IR *models* and a string; there is no user object in reach to invoke.
"""

from gebra.versioning.classify import (
    FIELD_COMPONENTS,
    canonical_view,
    changed_components,
    component_bytes,
    component_slice,
    components_for_path,
    next_version,
)
from gebra.versioning.models import (
    COMPONENT_COUNT,
    MAX_LABEL_LENGTH,
    Component,
    Version,
    VersionFormatError,
    VersionFormatErrorReason,
)

__all__ = [
    "COMPONENT_COUNT",
    "FIELD_COMPONENTS",
    "MAX_LABEL_LENGTH",
    "Component",
    "Version",
    "VersionFormatError",
    "VersionFormatErrorReason",
    "canonical_view",
    "changed_components",
    "component_bytes",
    "component_slice",
    "components_for_path",
    "next_version",
]
