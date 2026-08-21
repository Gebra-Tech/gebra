"""The stock binding-wrapper enumeration — INTROSPECTION-SPEC §7.4 (a) as amended by DEC-21.

Normative authority: INTROSPECTION-SPEC **§7.4 (a)** (ratified — DEC-15, amended — DEC-21,
2026-08-04), which locates a ``config_digest`` carrier "through any chain of ``RunnableBinding``
wrappers — including the enumerated STOCK langchain-core ``RunnableBinding`` subclasses admitted
by exact type (``_ChatModelBinding`` at the pinned substrate; enumeration per A1-D21; non-stock
subclasses stay declined per the DEC-20 stockness discipline)". The enumeration itself is the
research note's addendum **A1-D21**, verified at langchain-core 1.5.2.

**Why an enumeration rather than an ``issubclass`` check.** Every gate on the extraction path
matches composition classes by *exact type*, and that is a never-invokes posture rather than a
lookup strategy (DEC-20 / PD-025, and :data:`gebra.extraction.lcel.FRAGMENT_CLASSES` says so at
length): a ``RunnableBinding`` subclass can answer ``bound`` or ``kwargs`` with a property of its
own, and reading it would run that code inside ``gebra.extract()`` (§1 rule 3 admits no such
call). Widening the gate to *every* subclass would give that up. Widening it to a **named set of
substrate classes** does not: the same line DEC-19 draws for the drawing hazard and
:mod:`gebra.extraction.lcel`'s deps gate draw for theirs — LangChain's own attribute access on
LangChain's own objects is library work — applied to composition members.

**What the admission buys, said plainly.** ``BaseChatModel.bind()`` has answered with
``_ChatModelBinding`` since langchain-core 1.4.0, so before this admission
``prompt | model.bind(tools=…)`` was declined at the composition gate: the model got no node of
its own and therefore **no ``config_digest``** — the ``bind(tools=…)`` fingerprint gap DEC-21
closes. Two consequences, both ruled and neither incidental:

* a tool-bound model now carries a ``config_digest`` whose ``"bound"`` member reflects the tool
  overlay, so a tool-set edit moves ``graph_version`` the way a prompt edit does;
* the node set for such a workflow gains the model's node, which **moves ``graph_version``**.
  DEC-21 rules that movement deliberate and pre-release ("no consumers"), and it also closes an
  EX-17 finding: below core 1.4.0 ``bind()`` returns the stock class, which the gate already
  admitted, so the same authored workflow extracted to a *different node set* on different cells
  of the frozen VERSION-COMPAT §3 matrix. After this admission both ends agree.

**Version portability, and what happens when the substrate moves.** The table below is resolved
against the *installed* substrate: a name that is absent — as ``_ChatModelBinding`` is on every
langchain-core below 1.4.0 — contributes nothing, and the gate then behaves exactly as it did
before DEC-21 for the classes that do not exist there. A name that is present but is not a
``RunnableBinding`` subclass is likewise ignored: the fallback is always the conservative
direction (decline, warn, under-report), never an unchecked read. Drift is not left to that
silence, though — ``tests/extraction/test_stock.py`` re-derives the enumeration from the
installed substrate and fails if it disagrees with this table, which is A1-D21's own re-enumerate
instruction made executable.

**Never-invokes.** Resolving the table reads a module attribute and asks ``issubclass`` about two
*substrate* classes; the predicate below compares class objects with ``is`` and asks nothing of
them at all — no ``hash``, no ``==``, no ``repr``, so a caller-supplied metaclass never runs
(the reason :func:`gebra.extraction.digests.coerce` and
:func:`gebra.extraction.lcel.kind_of` spell their dispatches the same way). Importing this module
imports no more of the substrate than :mod:`gebra.extraction.digests` already does.
"""

from __future__ import annotations

import importlib
from typing import Final

from langchain_core.runnables.base import RunnableBinding

__all__ = [
    "ADMITTED_BINDING_CLASSES",
    "STOCK_BINDING_NAMES",
    "STOCK_BINDING_SUBCLASSES",
    "is_binding",
]

#: A1-D21's enumeration, as ``(module, qualname)`` pairs — the spelling the addendum uses
#: (``langchain_core.language_models.chat_models:_ChatModelBinding``) and the one a re-enumeration
#: against a new substrate version compares against.
#:
#: **By name, not by walking ``__subclasses__()``.** A1-D21 gives the walk as the *drift probe*,
#: and a probe is not a gate: ``RunnableBinding.__subclasses__()`` also reports the pydantic
#: generic parametrizations (``RunnableBinding[LanguageModelInput, AIMessage]``, created on demand
#: by ``__class_getitem__`` and cached per process), so a gate built on it would admit classes
#: whose very existence depends on what else the process happened to import. Node ids and digests
#: are downstream of this gate; §7.4 (e) makes them a function of the source objects' values and
#: classes and of nothing else.
STOCK_BINDING_NAMES: Final[tuple[tuple[str, str], ...]] = (
    ("langchain_core.language_models.chat_models", "_ChatModelBinding"),
)


def _resolve(names: tuple[tuple[str, str], ...]) -> tuple[type, ...]:
    """The classes ``names`` denotes on the installed substrate, in table order.

    A name absent from this substrate is skipped rather than raising: the enumeration is pinned
    to langchain-core 1.5.2 (A1-D21) and the tested matrix reaches back to 1.1, where
    ``_ChatModelBinding`` does not exist and ``bind()`` answers with the stock class the gate
    already admits. An object that is present but is not a ``RunnableBinding`` subclass is
    skipped too — the conservative direction, since admitting it is what would read an unknown
    class's composition members.
    """
    resolved: list[type] = []
    for module_name, attribute in names:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - every tested cell ships the module
            continue
        candidate = getattr(module, attribute, None)
        if isinstance(candidate, type) and issubclass(candidate, RunnableBinding):
            resolved.append(candidate)
    return tuple(resolved)


#: :data:`STOCK_BINDING_NAMES` resolved against the installed substrate — empty on a
#: langchain-core that has none of them.
STOCK_BINDING_SUBCLASSES: Final[tuple[type, ...]] = _resolve(STOCK_BINDING_NAMES)

#: Every class §7.4 (a) admits as a binding wrapper: the stock ``RunnableBinding`` itself and the
#: enumerated stock subclasses. Matched by identity — see :func:`is_binding`.
ADMITTED_BINDING_CLASSES: Final[tuple[type, ...]] = (RunnableBinding, *STOCK_BINDING_SUBCLASSES)


def is_binding(holder: type) -> bool:
    """Whether ``holder`` **is** one of the §7.4 (a) admitted binding classes.

    Identity only, never ``==`` and never a ``dict`` lookup: both would run a caller-supplied
    metaclass's ``__eq__``/``__hash__`` on the way to a miss, which is foreign code inside
    ``gebra.extract()`` (§1 rule 3). ``holder`` is a *class* — callers pass ``type(obj)`` — so a
    subclass of an admitted class answers ``False``, which is the whole point of the gate.
    """
    return any(holder is admitted for admitted in ADMITTED_BINDING_CLASSES)
