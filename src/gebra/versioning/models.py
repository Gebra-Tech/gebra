"""The V.S.F.E label — its grammar, its order, and what a bump does to it.

Normative authority: SOW §1's vocabulary table ("V.S.F.E — the snapshot version scheme: S
bumps on topology change, F on node/contract change, E on state-schema change") and brief
D-11 In-Scope 2 ("parser, comparator, and bump logic: compare the working IR against the
latest snapshot and bump S (topology), F (node/contract), and/or E (state schema)
accordingly"). IR-SPEC §4.1 names the label as the envelope's ``version`` field and gives
its semantics to brief D-11 — this module and :mod:`gebra.versioning.classify` are where
that is spent.

Three things the frozen package leaves to whoever implements the scheme, decided here and
stated where the decision bites:

**The grammar** (:data:`_LABEL_PATTERN`) — four non-negative decimal integers separated by
``.``, ASCII digits only, no leading zeros, no sign, no ``v`` prefix, rendered length at
most :data:`MAX_LABEL_LENGTH`. Leading zeros are refused because the label *is* a file name
— PD-012 fixes "that the V.S.F.E string is used verbatim as the snapshot/report file base
name, not the string's own grammar" — so two spellings of one version would be two files
holding one version. Refusing them makes rendering injective:
distinct labels name distinct versions and distinct versions render to distinct labels.

**The order** (:meth:`Version.__lt__`, generated) — component-wise *numeric* comparison, V
then S then F then E. Numeric, not lexicographic: ``1.10.0.0`` is later than ``1.9.0.0``,
which a string comparison of the labels gets backwards. The order is total and is defined
only between versions.

**The bump** (:meth:`Version.bump`) — increments each named component and **resets
nothing**. D-11 In-Scope 2 writes "bump S, F, *and/or* E accordingly": the three are
independent counters over their own domains, not a semver-style precedence chain where the
lesser components restart. A change touching topology and Σ lands on both S and E, and the
F counter still reads how many contract changes this workflow has seen.

**V is never derived.** The frozen package defines S, F and E and says nothing about what V
counts. This engine therefore assigns it to nothing: it is the caller's to set, every bump
carries it through unchanged, and :meth:`Component.derived` is the triple the engine will
select from a workflow change.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

__all__ = [
    "COMPONENT_COUNT",
    "MAX_LABEL_LENGTH",
    "Component",
    "Version",
    "VersionFormatError",
    "VersionFormatErrorReason",
]

#: How many components a label carries. Fixed at four by the scheme's own name.
COMPONENT_COUNT: Final = 4

#: The longest label this engine will produce or accept. It is SD-01's path-safety floor
#: (``gebra.store.MAX_VERSION_LENGTH``), restated rather than imported so that the version
#: engine stands on its own — the card's "usable independently of the store". The two are
#: held equal by ``tests/versioning/test_models_properties.py``, which also holds every
#: renderable version to the store's own ``VersionLabel`` validator.
MAX_LABEL_LENGTH: Final = 64

#: A component: ``0``, or a digit string with no leading zero. ``[0-9]`` rather than ``\d``
#: on purpose — ``\d`` matches Unicode decimal digits, and ``١.٠.٠.٠`` is not a label the
#: store can compare, sort, or safely put on a POSIX and a Windows filesystem alike.
_COMPONENT_PATTERN: Final = r"(?:0|[1-9][0-9]*)"

#: The whole label. ``fullmatch`` is what applies it, so no anchors and no whitespace
#: tolerance: a trailing newline or a space is a malformed label, not a parseable one.
_LABEL_PATTERN: Final = re.compile(rf"{_COMPONENT_PATTERN}(?:\.{_COMPONENT_PATTERN}){{3}}")

#: Same shape, but tolerant of leading zeros — used only to tell a *typo* apart from a
#: string that was never a version, so the error message can say which.
_LOOSE_PATTERN: Final = re.compile(r"[0-9]+(?:\.[0-9]+){3}")


class Component(str, Enum):
    """One position of a V.S.F.E label, in the order the label writes them.

    ``str`` mixin so a component is usable as a mapping key, a report field and a CLI token
    without a conversion step (the enums in :mod:`gebra.store` and :mod:`gebra.ir` are
    spelled the same way).

    Attributes:
        V: The leading component. **This engine never derives a V bump** — the frozen
            package defines S, F and E and leaves V unstated, so assigning it is the
            caller's call and every computed bump preserves it.
        S: Topology — nodes, edges, and START/END wiring (D-11 Context).
        F: Node/contract — the per-node contract and the graph-level ``runtime`` block
            (:mod:`gebra.versioning.classify` is where that mapping is stated).
        E: State schema — the Σ mapping (D-11 Context).
    """

    V = "V"
    S = "S"
    F = "F"
    E = "E"

    @classmethod
    def derived(cls) -> tuple[Component, ...]:
        """The components a workflow change can select — ``(S, F, E)``, never ``V``."""
        return (cls.S, cls.F, cls.E)


class VersionFormatErrorReason(str, Enum):
    """Why a label or a component tuple was refused — a stable code to branch on."""

    MALFORMED = "malformed"
    """Not four dot-separated ASCII decimal components."""

    LEADING_ZERO = "leading-zero"
    """Four components, but one is written with a leading zero (``1.01.0.0``)."""

    NEGATIVE = "negative"
    """A component below zero. Reachable only by construction — no label parses to one."""

    TOO_LONG = "too-long"
    """Longer than :data:`MAX_LABEL_LENGTH`, so it could not be a snapshot's file name."""


class VersionFormatError(ValueError):
    """A string that is not a V.S.F.E label, or components that could not render as one.

    A ``ValueError`` because that is what a failed parse is; the :attr:`reason` is what a
    caller branches on, and the message is what a person reads.

    Attributes:
        reason: The :class:`VersionFormatErrorReason` code.
        value: What was refused — the offending string, or the rendering of the offending
            components.
    """

    def __init__(self, message: str, *, reason: VersionFormatErrorReason, value: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.value = value


@dataclass(frozen=True, order=True, slots=True)
class Version:
    """A parsed V.S.F.E label — four counters, ordered and bumpable.

    Frozen, so a version can be a dict key and cannot be mutated out from under a store
    that has written it; ``order=True`` gives the component-wise numeric comparison
    described in the module docstring, which is exactly tuple order over the fields in
    declaration order.

    Construction validates: components are non-negative, and the rendering fits
    :data:`MAX_LABEL_LENGTH`. That keeps a total claim true — *every* :class:`Version`
    renders to a label the ``.gebra/`` store accepts as a file base name.

        >>> Version.parse("1.4.2.0").bump(Component.S, Component.E)
        Version(v=1, s=5, f=2, e=1)
        >>> str(Version(1, 10, 0, 0)), Version(1, 10, 0, 0) > Version(1, 9, 0, 0)
        ('1.10.0.0', True)

    Attributes:
        v: The leading component — carried, never derived (see the module docstring).
        s: Topology.
        f: Node/contract.
        e: State schema.
    """

    v: int
    s: int
    f: int
    e: int

    def __post_init__(self) -> None:
        for component, count in zip(Component, self.counts, strict=True):
            # ``bool`` is an ``int`` subclass, and ``str(True)`` is not a count.
            if isinstance(count, bool) or not isinstance(count, int):
                raise VersionFormatError(
                    f"component {component.value} is {count!r}, which is not a whole "
                    "number of changes; a version's components are integers",
                    reason=VersionFormatErrorReason.MALFORMED,
                    value=repr(count),
                )
        rendered = ".".join(str(count) for count in self.counts)
        negative = [
            component.value
            for component, count in zip(Component, self.counts, strict=True)
            if count < 0
        ]
        if negative:
            raise VersionFormatError(
                f"{rendered!r} counts down: component(s) {', '.join(negative)} are below "
                "zero, and a version counts changes",
                reason=VersionFormatErrorReason.NEGATIVE,
                value=rendered,
            )
        if len(rendered) > MAX_LABEL_LENGTH:
            raise VersionFormatError(
                f"a version label is at most {MAX_LABEL_LENGTH} characters — it is used "
                f"verbatim as a snapshot's file name (PD-012) — and this one is "
                f"{len(rendered)}: {rendered!r}",
                reason=VersionFormatErrorReason.TOO_LONG,
                value=rendered,
            )

    @property
    def counts(self) -> tuple[int, int, int, int]:
        """The four components in label order, as a tuple — the value the order compares."""
        return (self.v, self.s, self.f, self.e)

    @classmethod
    def initial(cls) -> Version:
        """``1.0.0.0`` — what a workflow's first snapshot carries.

        The first version of a thing is a choice, not a derivation: no earlier IR exists to
        compare against, so nothing bumps. ``1.0.0.0`` rather than ``0.0.0.0`` because a
        stored snapshot *is* a first generation, and because it is the label PD-012 and
        SD-01 use throughout as the example of a well-formed one. A caller wanting a
        different starting point constructs it.
        """
        return cls(1, 0, 0, 0)

    @classmethod
    def parse(cls, label: str) -> Version:
        """The version ``label`` names.

        The inverse of :meth:`__str__`, exactly: ``Version.parse(str(version)) == version``
        for every version, and ``str(Version.parse(label)) == label`` for every label this
        accepts. Injectivity in both directions is why leading zeros are refused rather
        than tolerated — see the module docstring.

        Raises:
            VersionFormatError: with reason ``MALFORMED`` for anything that is not four
                dot-separated ASCII decimal components (wrong count, a sign, a ``v``
                prefix, surrounding whitespace, a Unicode digit), ``LEADING_ZERO`` for
                ``1.01.0.0``, or ``TOO_LONG`` past :data:`MAX_LABEL_LENGTH`.
        """
        if len(label) > MAX_LABEL_LENGTH:
            raise VersionFormatError(
                f"a version label is at most {MAX_LABEL_LENGTH} characters — it is used "
                f"verbatim as a snapshot's file name (PD-012) — and this one is "
                f"{len(label)}: {label!r}",
                reason=VersionFormatErrorReason.TOO_LONG,
                value=label,
            )
        if _LABEL_PATTERN.fullmatch(label) is None:
            if _LOOSE_PATTERN.fullmatch(label) is not None:
                canonical = ".".join(str(int(part)) for part in label.split("."))
                raise VersionFormatError(
                    f"{label!r} writes a component with a leading zero; a version has one "
                    f"spelling and it is {canonical!r} (the label is a file name — two "
                    "spellings would be two files for one version)",
                    reason=VersionFormatErrorReason.LEADING_ZERO,
                    value=label,
                )
            raise VersionFormatError(
                f"{label!r} is not a V.S.F.E label; the grammar is four dot-separated "
                "decimal counts with no leading zeros, e.g. '1.4.2.0' (V.S.F.E — S "
                "topology, F node/contract, E state schema)",
                reason=VersionFormatErrorReason.MALFORMED,
                value=label,
            )
        v, s, f, e = (int(part) for part in label.split("."))
        return cls(v, s, f, e)

    def __str__(self) -> str:
        """The label — ``"1.4.2.0"``. What the store uses as a snapshot's file base name."""
        return ".".join(str(count) for count in self.counts)

    def bump(self, *components: Component) -> Version:
        """This version with each of ``components`` incremented by one.

        Nothing is reset. D-11 In-Scope 2 has the engine "bump S (topology), F
        (node/contract), **and/or** E (state schema) accordingly" — the three count changes
        in their own domain independently, so a change touching topology and Σ produces
        ``1.4.2.0 → 1.5.2.1`` and leaves the contract count reading what it read.

        Two consequences worth stating, both property-tested:

        * **Any non-empty bump moves the version strictly forward** in the order — no
          component ever decreases and at least one increases — so a store's chronological
          order and its version order are the same order.
        * **Bumping is order-independent and repeat-safe**: naming a component twice in one
          call increments it once (``components`` is read as a set), and bumping S then E
          gives what bumping E then S gives.

        Calling it with no components returns this version unchanged, which is what an
        unchanged workflow gets. Whether an unchanged workflow is re-snapshot at all is
        :mod:`gebra.snapshot`'s idempotency policy, not this engine's.

        Raises:
            VersionFormatError: with reason ``TOO_LONG`` if the incremented version could
                no longer render as a snapshot's file name.
        """
        selected = frozenset(components)
        if not selected:
            return self
        bumped = tuple(
            count + int(component in selected)
            for component, count in zip(Component, self.counts, strict=True)
        )
        return Version(*bumped)
