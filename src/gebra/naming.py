"""How gebra names a *type* when it has to name one — INTROSPECTION-SPEC §7.4 (DEC-15).

One function, in a module with no dependencies, because two lanes need it and neither may
import the other. :mod:`gebra.extraction` names the type of an object it refuses (§2 "naming
the object type") and the type of a declared value it cannot read; :mod:`gebra.annotations`
names the type of a decorator argument it refuses. Putting the spelling here keeps it a
single definition: it is digest-adjacent (§7.4 (c)/(d) fixes it for class identities in
digest input), and two copies of a digest-adjacent spelling drift.

Both re-export it under their own names, so ``gebra.extraction.type_identity`` and
``gebra.extraction.base.type_identity`` continue to resolve.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

__all__ = ["type_identity"]


def type_identity(value: object) -> str:
    """``value``'s type as ``"<top-level package>:<qualname>"`` — e.g. ``"builtins:dict"``.

    The identity spelling INTROSPECTION-SPEC §7.4 (c)/(d) fixes for class identities in
    digest input (DEC-15), reused wherever this package names a *type* rather than a value:
    the object an :class:`~gebra.extraction.errors.ExtractionError` refuses, the ``source``
    reference of :class:`~gebra.extraction.envelope.ExtractedFrom`, and the value a
    :class:`~gebra.annotations.errors.GebraContractError` refuses.

    That last use is why naming a type rather than showing a value matters beyond tidiness:
    a message built with ``{value!r}`` runs the value's own ``__repr__``, so a decorator
    argument could replace gebra's error with an exception of its own. Nothing here is read
    off the object at all — only its type, and only through the **unbound descriptors the
    interpreter itself uses** (WA-07).

    **Both halves go through ``type.__dict__``, and neither has a rendering as a fallback.**
    ``cls.__qualname__`` and ``cls.__module__`` route through the *metaclass*, which may
    define ``__getattribute__`` and answer or observe the read — and this value is
    digest-bearing (§7.4 (d) rule 12 puts it inside ``config_digest``), so a metaclass could
    reach both a foreign-code route and a nondeterminism one. The unbound descriptors are the
    form :mod:`gebra.extraction.state` already uses, for the same reason. A fallback of
    ``repr(cls)`` would be worse than useless twice over: evaluated as a ``getattr`` default
    it runs on **every** call, eagerly, whether or not the name is missing; and what it runs
    is the metaclass's ``__repr__``. The name a class does not carry is named ``"<unnamed>"``
    and the package a class does not name is the empty string — a class that answers neither
    is not something a rendering would have told the truth about either.
    """
    cls = type(value)
    return f"{_package(cls)}:{_qualname(cls)}"


def _qualname(cls: type) -> str:
    """``cls``'s qualified name, read through the interpreter's own descriptor."""
    name = _unbound(cls, "__qualname__")
    if not isinstance(name, str):  # pragma: no cover - see :func:`_unbound`
        return "<unnamed>"
    return name


def _package(cls: type) -> str:
    """The top-level package of ``cls``'s module, read the same way.

    ``__module__`` is the half a class *can* answer with a non-string: it is an ordinary class
    dict entry, so ``cls.__module__ = 7`` is legal Python. A class that does that is named by
    its qualname alone rather than by a rendering of whatever it put there.
    """
    module = _unbound(cls, "__module__")
    if not isinstance(module, str):
        return ""
    return module.partition(".")[0]


def _unbound(cls: type, name: str) -> object:
    """One ``type`` slot of ``cls``, or ``None`` when the descriptor declines to answer.

    The broad ``except`` covers a class whose metaclass is not a ``type`` subclass at all,
    which the descriptor refuses — the same defensive shape and the same reasoning as
    :func:`gebra.extraction.state._qualname`: the alternative to a caught failure over a
    *name* is an aborted extraction, which no reading of INTROSPECTION §2 licenses.
    """
    try:
        return type.__dict__[name].__get__(cls)
    except Exception:  # noqa: BLE001  # pragma: no cover - defensive; see above
        return None
