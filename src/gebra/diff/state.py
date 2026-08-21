"""The state-schema diff — what moved inside Σ (E).

Brief D-11 In-Scope 4 has the engine report "state-schema keys" alongside nodes, edges and
contracts, and W6 is where that lands. This module is the Σ half: the E component of V.S.F.E,
which D-11's Context defines as "an E bump for state-schema Σ changes" and IR-SPEC §2.2
defines as the ``state`` mapping — each key declared either as a bare type-name string or as
``{type, reducer?, optional?}``.

**The delta mirrors the E slice exactly.** :func:`~gebra.versioning.classify.component_slice`
cuts E as ``{"state": …}``, and :class:`StateDelta` reports over precisely that: the key set,
each persisting key's declaration, and whether the block is there at all. Nothing else is in
E, and nothing in E is left out — which is what lets the bump class in
:mod:`gebra.diff.workflow` be *derived* from this delta rather than computed a second time.

**Granularity: per key, split into the three declared facets.** ``type``, ``reducer`` and
``optional`` are what IR-SPEC §2.2 says a Σ value is, and each is read by a different
consumer — ``reducer`` by P-09 on fan-in keys, ``optional`` by P-04 (a key carrying it is
treated as written at START), ``type`` by nobody in 1.0, where "types are opaque declared
strings … no type algebra is normatively imposed". Splitting them is what lets a reader see a
*retype* — a key kept but re-declared — as something other than a key removed and re-added,
which is the distinction brief D-11's canonical "read-key removal **or retype**" case turns
on.

**Both sides are read off the canonical view**, so §6.3's representation-normalization has
already run: ``{type: "str"}`` and the bare ``"str"`` are one declaration here exactly as they
are one digest, and an authored surface difference is never reported as a schema change.

**Absent and empty are different.** ``state`` absent and ``state: {}`` are different canonical
documents (``{}`` versus ``{"state":{}}``) and therefore different digests, so the delta
carries presence flags beside its key sets. A delta that only compared keys would report
nothing while the version moved — and since PD-012 makes the V.S.F.E label a file name, an
under-reported component is two workflow contents under one file.

**No verdicts.** A removed key that some node still declares in ``input`` is the shape brief
D-11 names as a canonical case, and this engine will report the removal — never that the
removal is breaking. P-12 ``evolution-safety`` is out of Phase-0 scope (SOW §8), its deferral
ratified by PD-006 R4, and whether any node reads a removed key is P-04's question over one
IR, not this diff's over two.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07): the input is an
IR model, and there is no user object in reach to invoke.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from gebra.diff.models import ledger_sort_key
from gebra.ir.canonical import canonical_foreign_bytes
from gebra.ir.models import WorkflowIR
from gebra.versioning.classify import canonical_view

__all__ = [
    "KeyDeclaration",
    "StateDelta",
    "StateKeyChanged",
    "StateKeyRef",
    "state_delta",
    "state_diff",
]


@dataclass(frozen=True, slots=True)
class KeyDeclaration:
    """One Σ value, as canonicalization leaves it (IR-SPEC §2.2, §6.3).

    The bare type-name string and the object form land on one value here, because they land
    on one canonical form: a value carrying neither ``reducer`` nor an ``optional`` flag
    *is* the bare string.

    Attributes:
        type: The declared type name — an opaque string in ir 1.0.
        reducer: The declared channel-merge function (``"operator.add"``), or ``None``.
        optional: ``True`` when the key is graph input or carries a default; ``None`` when no
            flag is declared, which canonicalization keeps distinct from ``False``.
    """

    type: str
    reducer: str | None = None
    optional: bool | None = None


@dataclass(frozen=True, slots=True)
class StateKeyRef:
    """A Σ key that appeared or disappeared, with the declaration it carried.

    Attributes:
        key: The state key.
        declaration: What that side declared for it.
    """

    key: str
    declaration: KeyDeclaration

    def sort_key(self) -> bytes:
        """The deterministic report order: ledger §6 on the key (keys are unique)."""
        return ledger_sort_key(self.key)


@dataclass(frozen=True, slots=True)
class StateKeyChanged:
    """A Σ key present on both sides whose declaration moved.

    Attributes:
        key: The state key, declared on both sides.
        before: Its declaration on the before side.
        after: Its declaration on the after side.
    """

    key: str
    before: KeyDeclaration
    after: KeyDeclaration

    @property
    def retyped(self) -> bool:
        """Whether the declared type moved — the "retype" of D-11's canonical case."""
        return self.before.type != self.after.type

    @property
    def reducer_changed(self) -> bool:
        """Whether the declared channel-merge function moved (P-09's input, §2.2)."""
        return self.before.reducer != self.after.reducer

    @property
    def optional_changed(self) -> bool:
        """Whether the ``optional`` flag moved (P-04 reads it as written-at-START, §2.2)."""
        return self.before.optional != self.after.optional

    def sort_key(self) -> bytes:
        """The deterministic report order: ledger §6 on the key."""
        return ledger_sort_key(self.key)


@dataclass(frozen=True, slots=True)
class StateDelta:
    """The E-level delta: the state schema Σ.

    Read it forward: ``added`` means declared on the after side only. Swapping the two sides
    swaps ``added`` with ``removed``, the halves of every :class:`StateKeyChanged`, and the
    two presence flags.

    Attributes:
        added: Keys declared only on the after side — D-11's "new optional state keys"
            extension lands here, carrying ``optional=True`` on its declaration.
        removed: Keys declared only on the before side.
        changed: Persisting keys whose declaration moved.
        present_before: Whether a ``state`` block was in the before side's canonical form.
        present_after: Whether one is in the after side's. The two differ when Σ arrived or
            was dropped wholesale — including the empty-versus-absent case, which moves the
            digest and which no key entry would show.
    """

    added: tuple[StateKeyRef, ...] = ()
    removed: tuple[StateKeyRef, ...] = ()
    changed: tuple[StateKeyChanged, ...] = ()
    present_before: bool = False
    present_after: bool = False

    @classmethod
    def of(
        cls,
        added: Iterable[StateKeyRef] = (),
        removed: Iterable[StateKeyRef] = (),
        changed: Iterable[StateKeyChanged] = (),
        present_before: bool = False,
        present_after: bool = False,
    ) -> StateDelta:
        """Build with every member sorted into the ledger §6 report order."""
        return cls(
            added=tuple(sorted(added, key=StateKeyRef.sort_key)),
            removed=tuple(sorted(removed, key=StateKeyRef.sort_key)),
            changed=tuple(sorted(changed, key=StateKeyChanged.sort_key)),
            present_before=present_before,
            present_after=present_after,
        )

    def __bool__(self) -> bool:
        return bool(
            self.added or self.removed or self.changed or self.present_before != self.present_after
        )


def state_delta(before_view: Mapping[str, Any], after_view: Mapping[str, Any]) -> StateDelta:
    """The Σ delta between two canonical views (IR-SPEC §6.1 steps 2–6, parsed).

    Internal to :mod:`gebra.diff` — the view-taking form, for a caller that already
    canonicalized both sides, as :func:`~gebra.diff.workflow.workflow_diff` has when it gets
    here. It is not part of the package's public surface, and it assumes what
    :func:`canonical_view` produces: hand-built mappings are the caller's risk.
    :func:`state_diff` is the same thing from two IRs, and is what a caller wants.
    """
    before_state = _values(before_view)
    after_state = _values(after_view)
    return StateDelta.of(
        added=[
            StateKeyRef(key, _declaration(after_state[key]))
            for key in after_state.keys() - before_state.keys()
        ],
        removed=[
            StateKeyRef(key, _declaration(before_state[key]))
            for key in before_state.keys() - after_state.keys()
        ],
        changed=[
            StateKeyChanged(key, _declaration(before_state[key]), _declaration(after_state[key]))
            for key in before_state.keys() & after_state.keys()
            # By canonical bytes, as everywhere else in this package (IR-SPEC §1.2): a Σ value
            # is a `str` or a three-member object today, so Python `==` would agree — but
            # nothing at this line would notice if a future 1.x facet were unconstrained, and
            # that is precisely the shape of the `args_schema` defect SD-02's pre-review found
            # (``True == 1``). The identity is the emitter's, not the interpreter's.
            if canonical_foreign_bytes(before_state[key])
            != canonical_foreign_bytes(after_state[key])
        ],
        present_before="state" in before_view,
        present_after="state" in after_view,
    )


def state_diff(before: WorkflowIR, after: WorkflowIR) -> StateDelta:
    """The Σ delta between two IRs.

    Raises:
        CanonicalizationError: if either IR carries a value the canonical form refuses
            (IR-SPEC §6.1 step 5) — such a document has no digest, so it has no version and
            nothing to diff against.
    """
    return state_delta(canonical_view(before), canonical_view(after))


def _values(view: Mapping[str, Any]) -> Mapping[str, Any]:
    """The canonical ``state`` object, or an empty one when the member is absent.

    Presence is read separately, by the caller, with ``in`` rather than truthiness — ``state``
    absent and ``state: {}`` are different canonical documents and different digests.
    """
    state: Any = view.get("state")
    if state is None:
        return {}
    typed: Mapping[str, Any] = state
    return typed


def _declaration(value: Any) -> KeyDeclaration:
    """One Σ value, for reporting — the comparison is by bytes, this is what a reader sees.

    Both surface forms §2.2 admits are handled, though only one of them can appear in a
    canonical view: §6.3 collapses an object carrying neither ``reducer`` nor an ``optional``
    flag to the bare type-name string.
    """
    if isinstance(value, str):
        return KeyDeclaration(type=value)
    field: Mapping[str, Any] = value
    declared_type: str = field["type"]
    return KeyDeclaration(
        type=declared_type,
        reducer=field.get("reducer"),
        optional=field.get("optional"),
    )
