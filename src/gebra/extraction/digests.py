"""Digest computation — the INTROSPECTION-SPEC §7.4 rule set (ratified — DEC-15).

Normative authority: INTROSPECTION-SPEC **§7.4** (a)…(e), which resolves the three IR-SPEC
§3.6 delegations that had no text behind them (spec defects SD-1…SD-3, ruled in PD-014 and
filed as vault DEC-15, 2026-07-31); IR-SPEC §3.6 for the slot shapes and the foreign-object
pipeline; §3's ``StateNodeSpec.runnable`` row purpose (iii) and §5's carrier note for where a
digest lands; §8's ``unsupported-construct`` row for the one warning case §7.4 adds. All under
the §1 never-invokes discipline.

**What the two slots are for.** ir 1.0 has no field for a prompt's text or a model's
parameters — deliberately: bodies never enter the IR, only fingerprints do (§3.6,
"hermeticity is preserved"). Without them two workflows differing only in prompt text extract
to identical documents with identical ``graph_version``s, which is the opaque-body gap the
Capability Audit named. A digest closes it without carrying the body: the slot is hash-scoped
(IR-SPEC §6.4), so editing a prompt moves ``graph_version`` exactly as editing an edge does.

**Carriers (a).** ``prompt_digest`` is computed for exactly the nodes whose *own bound object*
is a ``BasePromptTemplate``, ``config_digest`` for exactly the nodes whose own bound object is
a ``BaseLanguageModel``; neither is ever aggregated onto a parent. A model reached through
``RunnableBinding`` wrappers keeps the digest on the node that carries the *model* — the
wrapper contributes the ``"bound"`` overlay of (c) and carries no digest of its own. Under the
§5 stitching this build ships (ratified — DEC-20/PD-025 D1/D2), a bind frame contributes no
segment and ``%bind[…]`` names the object *inside* the binding, so (a)'s "binding-wrapper
node" is the node that *holds* the binding — ``%seq[1]`` in ``prompt | binding`` — and the
model-carrying node is its ``%bind[0]`` child. PD-014's parenthetical spells the token the
other way round because it predates DEC-20; the rule it states is unchanged and is what
:func:`digests_for` implements. Which classes count as "``RunnableBinding`` wrappers" is
:mod:`gebra.extraction.stock`: the stock class and the enumerated stock subclasses (A1-D21),
admitted by exact type per (a) as amended by DEC-21 — the amendment that lets
``prompt | model.bind(tools=…)`` carry a ``config_digest`` at all.

**Everything here is a pure function of the source objects' values and classes (e).** No time,
no address, no environment, no construction provenance: two conforming extractors given equal
source objects MUST produce string-equal digests. Three places that would have broken it, and
what is done instead:

* **Sets.** A ``set``-valued parameter iterates in an order that varies with the process's
  string-hash seed. (d) rule 11 sorts the members by each coerced member's own JCS bytes,
  which is the device IR-SPEC §6.2 already uses for ``edges[]``.
* **``repr``.** Every rejected byte-source option reached ``repr`` of a plumbing object, whose
  ``0x…`` address is run-dependent — and whose ``__repr__`` is foreign code besides (PD-014
  finding 3). (d) rule 12 substitutes the *class identity* instead, so a swapped client class
  still moves the digest while nothing about a particular object's lifetime does.
* **Numbers.** PD-004 forbids NaN/Infinity and integers outside ±(2⁵³−1) anywhere the pipeline
  serializes. (d) rules 5–6 replace them with markers *before* the pipeline sees them, so a
  model holding one still extracts (§2: extraction is total; hard failure only at the object
  boundary) and the digest still records that something unrepresentable was there.

**Never-invokes.** This path reaches for no property, method or ``repr`` of a source object.
Containers and scalars are read through unbound built-in accessors, the way
:func:`gebra.ir.canonical.canonical_bytes` reads foreign content, so no subclass hook runs; an
``Enum``'s value comes off the unbound ``enum.Enum`` descriptor rather than through
``getattr``, so a member class that shadowed ``value`` does not get to answer; a mapping's keys
are never hashed, compared or stringified, and neither are their **classes** — every type
dispatch here is an identity test, because a ``dict`` keyed by class calls the metaclass's
``__hash__`` and a tuple membership test falls through to its ``__eq__``. A class identity is
built from the unbound ``type`` descriptors (:func:`gebra.naming.type_identity`), so a
metaclass never sees that read either. The reads that *are* made are the ones §1 rule 3 admits
by name: attribute reads, ``isinstance`` checks, and pydantic model introspection.

**Two residues on the config surface, stated rather than denied.** §7.4 (c) prescribes
``type(m).model_fields`` + ``getattr(m, name)`` — the hazard-free read, since PD-014 finding 4
rejected ``_identifying_params``/``lc_attributes`` precisely because they are *properties* —
and asserts in the same breath that "No property, method, or ``repr`` read ever runs on the
model object". That second sentence is not guaranteed by the first, twice over on the pinned
substrate:

* pydantic strips a field-shadowing class attribute only from the class being built, so a
  ``@property`` on a **base** plus the annotation on the subclass leaves a live data
  descriptor above the instance dict — and a data descriptor resolves ahead of ``__dict__``,
  so the getter runs and its return value is digested;
* ``BaseModel.__getattr__`` raising ``AttributeError`` is what makes (e)'s ``model_construct``
  degrade sound, and a subclass ``__getattr__`` overrides it, feeding a computed value into
  the digest instead of triggering the degrade.

This build performs the read (c) prescribes and improvises no shield around it — reading
``__dict__`` instead would change the digested bytes for those classes, which is exactly the
improvising WA-03 forbids. Both shapes have armed fixtures so the residue is **counted** rather
than described (``tests/sample_workflows/sentinel_digests.py``), and the spec-accuracy question
is filed as PD-029. The prompt branch has no matching residue: every attribute it reads sits
behind an exact-type gate, so an unrecognised template or item is decided from ``type()`` and
never read at all. One residue is package-wide and already named by
:func:`gebra.naming.type_identity`: deciding what a class *is* takes one descriptor read, which
a sufficiently exotic metaclass observes.

**What is deliberately insensitive**, per (b) and the frozen §3.6 string-template sentence:
``template_format`` (an f-string and a jinja2 template with identical text share a digest),
``input_variables`` and ``partial_variables``. And per (c): ``RunnableConfig`` content —
``with_config``'s tags, metadata, callbacks, run name and ``configurable`` — which is
observability and invoke wiring rather than generation config. Both are documented limits of
the "did the prompt text change?" fingerprint rather than gaps.

**One residual risk, stated rather than buried** (PD-014 Q2s, resolved as recommended at
ratification): secrets are excluded *by value type*. A provider that keeps its key in a
``SecretStr`` field is excluded; one that keeps it in a plain ``str`` field is not, so for that
provider rotating the key moves ``config_digest``. Excluding by field name would mean reading
``lc_secrets``, a langchain-authored **property**, which §1 rule 3 does not admit. Widening the
exclusion is a named 1.x item.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import (
    AIMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import (
    AIMessagePromptTemplate,
    ChatMessagePromptTemplate,
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    PromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.prompts.base import BasePromptTemplate
from pydantic import SecretStr

from gebra.extraction.base import type_identity
from gebra.extraction.stock import is_binding
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode
from gebra.ir.canonical import (
    I_JSON_MAX_INT,
    I_JSON_MIN_INT,
    CanonicalizationError,
    Json,
    canonical_foreign_bytes,
    render_digest,
)

__all__ = [
    "UNREPRESENTABLE",
    "NodeDigests",
    "PromptGap",
    "coerce",
    "config_form",
    "digests_for",
    "prompt_form",
]

#: The member name (d) gives every unrepresentable-value marker. One key, one object shape, so
#: a marker is distinguishable from authored content by inspection — a config that really held
#: ``{"__gebra_unrepresentable__": …}`` as data would not be, which is the same collision (b)
#: records for a string template that *is* some structured form's JCS text: an accepted
#: residual rather than one papered over.
UNREPRESENTABLE: Final = "__gebra_unrepresentable__"

#: (b)'s fixed-role message-template row: exact class → the role constant it digests as. The
#: role is a *constant* here and is read from the object for the static-message row below,
#: which is (b)'s own asymmetry: a template class fixes its role in its type, while a message
#: carries it in a field.
#:
#: **A sequence compared with ``is``, not a mapping keyed by the class** — the same reason
#: :func:`gebra.extraction.lcel.kind_of` matches by identity. A ``dict`` lookup keyed on
#: ``type(item)`` calls ``hash()`` on that class, and a tuple membership test falls through to
#: ``==`` on every miss; both run the **metaclass's** ``__hash__``/``__eq__``, which on a
#: caller-supplied class is user code inside ``gebra.extract()`` (§1 rule 3). Identity
#: comparison asks nothing of the class at all.
_TEMPLATE_ROLES: Final[tuple[tuple[type, str], ...]] = (
    (SystemMessagePromptTemplate, "system"),
    (HumanMessagePromptTemplate, "human"),
    (AIMessagePromptTemplate, "ai"),
)

#: (b)'s static-message row: the exact classes whose ``type`` field is the digested role.
#: Matched by identity, for the reason above.
_STATIC_MESSAGES: Final[tuple[type, ...]] = (SystemMessage, HumanMessage, AIMessage)


def _one_of(holder: type, classes: tuple[type, ...]) -> bool:
    """Whether ``holder`` **is** one of ``classes`` — identity only, never ``==``."""
    return any(holder is candidate for candidate in classes)


#: The construct slug of the one §8 emission case §7.4 adds — an object, item or part outside
#: (b)'s closed vocabulary, for which the digest is **absent for that node, never partial**.
_TEMPLATE_NOT_CARRIED: Final = "prompt-template-not-carried"

#: The construct slug of (e)'s recorded implementer edge: a ``model_fields`` name absent from
#: the instance's ``__dict__``, reachable only through ``model_construct()``.
_MODEL_FIELD_UNREADABLE: Final = "model-field-unreadable"

#: ``enum.Enum.value`` as an unbound descriptor. (d) rule 4 unwraps an ``Enum`` to
#: ``K(value)``; going through ``getattr`` would let a member class that shadowed ``value``
#: with a property of its own answer the question, which is the foreign-code read §1 rule 3
#: excludes. ``enum.Enum.value`` cannot be spelled directly — it is a ``DynamicClassAttribute``
#: that refuses class access — so the descriptor is taken out of the base class's ``__dict__``.
_ENUM_VALUE: Final = enum.Enum.__dict__["value"].__get__


@dataclass(frozen=True)
class NodeDigests:
    """What §7.4 has to say about one node.

    Attributes:
        prompt: The node's ``prompt_digest``, or ``None`` — absent because the node carries no
            template at all, or because (b)'s honest fallback applied and ``warnings`` says so.
        config: The node's ``config_digest``, or ``None`` — absent because the node carries no
            model, or because (e)'s ``model_construct`` edge applied.
        warnings: The §8 records, empty in every ordinary case. (c) makes ``config_digest``
            "Full on every discovered model node", so a config-side warning is the recorded
            edge rather than a routine outcome.
    """

    prompt: str | None = None
    config: str | None = None
    warnings: tuple[ExtractionWarning, ...] = ()

    def __bool__(self) -> bool:
        """Whether this node carries a digest — what a caller assembling ``annotations`` asks."""
        return self.prompt is not None or self.config is not None


@dataclass(frozen=True)
class PromptGap:
    """Why (b)'s closed vocabulary admitted no digest, in the terms §8's row asks for.

    Attributes:
        identity: The offender's class identity, per §8 ("carrying the offender's class
            identity"). A class name, never a rendering of the value — naming the type is what
            keeps the record free of the body the slot exists *not* to carry, and free of the
            ``__repr__`` call that would run foreign code.
        where: Where in the template it sat, in the location shape §8's row names: the item
            index for a message, and the part index below it for a multi-part content
            template.
    """

    identity: str
    where: Mapping[str, Json] = field(default_factory=dict)


def digests_for(node_id: str, bound: object, *, bindings: Sequence[object] = ()) -> NodeDigests:
    """The digests node ``node_id`` carries, per §7.4 (a).

    Args:
        node_id: The node's escaped IR-SPEC §5 id — what any §8 record is filed under.
        bound: The node's **own** bound object: ``StateNodeSpec.runnable`` on the §3 path, the
            stitched child on the §5 path. (a) quantifies over exactly this object — a
            composite that merely *contains* a template carries nothing, because digests are
            never aggregated onto parents.
        bindings: The enclosing ``RunnableBinding`` chain, **outermost first** — the frames (a)
            means by "located through any chain of ``RunnableBinding`` wrappers", and the
            source of (c)'s ``"bound"`` overlay. Empty where the node's object is not inside
            one.

    Returns:
        The :class:`NodeDigests` record. Nothing here raises: every way of failing to produce a
        digest is an absent slot plus a §8 record, because §2 puts hard failure at the object
        boundary and nowhere else.
    """
    if isinstance(bound, BasePromptTemplate):
        return _prompt_digest(node_id, bound)
    if isinstance(bound, BaseLanguageModel):
        return _config_digest(node_id, bound, bindings)
    return NodeDigests()


# ── (b) the prompt byte source ───────────────────────────────────────────────────────────


def prompt_form(template: object) -> bytes | PromptGap:
    """(b)'s digest input for ``template``: its bytes, or the gap that has none.

    The two recognised shapes:

    * **exact type** ``PromptTemplate`` — the UTF-8 encoding of its ``template`` string,
      byte-exact. This restates frozen IR-SPEC §3.6: no trimming, no normalization, and
      deliberately no NFC (§6.3's NFC applies to identifier-role strings, which a prompt is
      not).
    * **exact type** ``ChatPromptTemplate`` — the JCS serialization of the prompt canonical
      form M, a JSON array over ``messages`` in **authored order** (order is semantic here, so
      §6.2's array sorts do not apply).

    Exact type, not ``isinstance``, is what makes the vocabulary closed: a
    ``FewShotPromptTemplate`` is a ``BasePromptTemplate`` whose examples this build has no
    encoding for, so it takes the honest fallback rather than digesting the subset it happens
    to understand. Extending the vocabulary is an additive future DEC (§7.4 (b)), never an
    extractor's improvisation.
    """
    holder = type(template)
    if holder is PromptTemplate:
        return _string_template_bytes(template)
    if holder is ChatPromptTemplate:
        return _chat_template_bytes(template)
    return PromptGap(type_identity(template))


def _string_template_bytes(template: object) -> bytes | PromptGap:
    """A ``PromptTemplate``'s own bytes — frozen IR-SPEC §3.6's "exact UTF-8 bytes".

    The one shape with no bytes is a ``template`` string that has no UTF-8 encoding at all: a
    lone surrogate is not a Unicode scalar value, so "the exact UTF-8 bytes of the template"
    names nothing. §3.6 fixes the byte source and offers no substitute, and inventing one would
    be a silent digest divergence, so this takes (b)'s honest fallback — absent digest, one
    record — which is the posture (e) gives its own recorded implementer edge.
    """
    text = getattr(template, "template", None)
    if not isinstance(text, str):
        # The offender §8's row names is the *class that could not be digested* — here the
        # template, not the type of what it holds, which rides as `found` instead. Same
        # spelling as every other gap, so a consumer branching on `offender` reads one thing.
        return PromptGap(
            type_identity(template), {"member": "template", "found": type_identity(text)}
        )
    try:
        return str.encode(text, "utf-8")
    except UnicodeEncodeError:
        return PromptGap(type_identity(template), {"member": "template", "why": "lone-surrogate"})


def _chat_template_bytes(template: object) -> bytes | PromptGap:
    """The prompt canonical form M of a ``ChatPromptTemplate``, serialized per RFC 8785.

    One element per item of ``messages``, in authored order, over (b)'s six item rows. An item
    outside them takes the whole node's digest with it — "``prompt_digest`` absent for that
    node (never a partial digest)" — because a digest over the messages this build happened to
    recognise would be a fingerprint of something the author never wrote.
    """
    items = getattr(template, "messages", None)
    if not isinstance(items, list):
        return PromptGap(
            type_identity(template), {"member": "messages", "found": type_identity(items)}
        )
    form: list[Json] = []
    for index, item in enumerate(list.__iter__(items)):
        element = _message_form(item, index)
        if isinstance(element, PromptGap):
            return element
        form.append(element)
    return canonical_foreign_bytes(form)


def _authored(item: object, member: str, index: int) -> Json | PromptGap:
    """One **required** authored member of an M element, coerced — or the gap its absence is.

    Every scalar that reaches M goes through :func:`coerce` on the way in. For the values (b)'s
    rows actually carry that is the identity; for a pathological one — a role string holding a
    lone surrogate, an ``n_messages`` outside the I-JSON range — it is (d)'s deterministic
    marker rather than an exception out of ``gebra.extract()``.

    **An absent member is a gap, not a null**, and that is what keeps (b)'s sentence literal.
    These members are REQUIRED on their classes, so only a ``model_construct``ed object can
    lack one — but if one did, ``coerce`` would answer ``null``, the §3.6 pipeline would *drop*
    the member, and the digested bytes would be a JCS document over a shape the author never
    wrote. Treating it as (b)'s honest fallback instead is the same disposition the three
    sibling ``model_construct`` shapes already take, and it leaves the foreign-object
    pipeline's null-member rule with nothing to drop — so "the digested bytes are the JCS
    serialization of M" holds without a proviso.
    """
    value = getattr(item, member, None)
    if value is None:
        return PromptGap(type_identity(item), {"item": index, "member": member})
    return coerce(value)


def _message_form(item: object, index: int) -> Json | PromptGap:
    """One element of M — (b)'s six item rows, matched by exact type."""
    holder = type(item)
    for template, role in _TEMPLATE_ROLES:
        if holder is template:
            return _message_template_form(role, item, index)
    if holder is ChatMessagePromptTemplate:
        return _message_template_form(_authored(item, "role", index), item, index)
    if holder is MessagesPlaceholder:
        return _placeholder_form(item, index)
    if _one_of(holder, _STATIC_MESSAGES) or holder is ChatMessage:
        # A static message's role is read off the object: ``type`` is the class's own constant
        # for the three fixed kinds, while ``ChatMessage.type`` is the constant ``"chat"`` and
        # drops the authored role — so (b) reads ``role`` there instead (one of the four
        # encoding amendments folded in at ratification).
        member = "role" if holder is ChatMessage else "type"
        return _object(
            ("role", _authored(item, member, index)),
            ("content", _authored(item, "content", index)),
        )
    if holder is ToolMessage:
        return _object(
            ("role", "tool"),
            ("tool_call_id", _authored(item, "tool_call_id", index)),
            ("content", _authored(item, "content", index)),
        )
    return PromptGap(type_identity(item), {"item": index})


def _object(*members: tuple[str, Json | PromptGap]) -> Json | PromptGap:
    """Assemble one M element, or hand back the first gap among its members.

    A gap anywhere in an element takes the whole node's digest, per (b) rule 4's "never a
    partial digest" — so it propagates rather than being filled in with a placeholder.
    """
    assembled: dict[str, Json] = {}
    for name, value in members:
        if isinstance(value, PromptGap):
            return value
        assembled[name] = value
    return assembled


def _message_template_form(role: Json | PromptGap, item: object, index: int) -> Json | PromptGap:
    """A message *template* element: ``{"role": …, "template": E(prompt)}`` (b).

    ``E(p)`` is the inner template's own text, or — for a multi-part content template — a JSON
    array of the parts' texts, string-template parts only. A part outside that is a gap at the
    part's own index, which is what lets the record say *where* rather than only *that*.
    """
    return _object(
        ("role", role),
        ("template", _inner_template_form(getattr(item, "prompt", None), index)),
    )


def _inner_template_form(inner: object, index: int) -> Json | PromptGap:
    """E(p) of (b): the inner ``PromptTemplate``'s text, or the parts' texts as an array."""
    if type(inner) is PromptTemplate:
        return _authored(inner, "template", index)
    if isinstance(inner, list):
        parts: list[Json] = []
        for part_index, part in enumerate(list.__iter__(inner)):
            if type(part) is not PromptTemplate:
                return PromptGap(type_identity(part), {"item": index, "part": part_index})
            text = _authored(part, "template", index)
            if isinstance(text, PromptGap):
                return text
            parts.append(text)
        return parts
    return PromptGap(type_identity(inner), {"item": index, "member": "prompt"})


def _placeholder_form(item: object, index: int) -> Json | PromptGap:
    """A ``MessagesPlaceholder`` element (b).

    ``optional`` rides only when it is true and ``n_messages`` only when it is set, both
    omitted otherwise — so the ordinary placeholder digests as the one-member object (b)
    writes, and a placeholder carrying either fact digests differently from one that does not.
    (``n_messages`` joined the encoding as one of the four amendments folded in at
    ratification: it is part of the authored shape and was silently undigested in the draft.)
    Only ``variable_name`` is required, so only it can be a gap.
    """
    form = _object(("placeholder", _authored(item, "variable_name", index)))
    if isinstance(form, PromptGap) or not isinstance(form, dict):  # pragma: no cover - _object
        return form
    if getattr(item, "optional", None) is True:
        form["optional"] = True
    limit = getattr(item, "n_messages", None)
    if limit is not None:
        form["n_messages"] = coerce(limit)
    return form


def _prompt_digest(node_id: str, template: object) -> NodeDigests:
    """``prompt_digest`` for one carrier: (b)'s bytes through §6.1 steps 7–8, or the record."""
    payload = prompt_form(template)
    if isinstance(payload, PromptGap):
        return NodeDigests(
            warnings=(
                _unsupported(
                    node_id,
                    _TEMPLATE_NOT_CARRIED,
                    (
                        f"{payload.identity} is outside the closed prompt-template vocabulary "
                        "INTROSPECTION-SPEC §7.4 (b) fixes, so this node's prompt_digest is "
                        "absent rather than computed over the part of the template this build "
                        "recognises"
                    ),
                    {"offender": payload.identity, **dict(payload.where)},
                ),
            )
        )
    return NodeDigests(prompt=render_digest(payload))


# ── (c) the config surface ───────────────────────────────────────────────────────────────


def config_form(model: object, bindings: Sequence[object] = ()) -> dict[str, Json] | None:
    """The config canonical form C of (c), or ``None`` for (e)'s ``model_construct`` edge.

    Three members:

    * ``"provider"`` — the model's class identity, which is what makes swapping providers a
      digest change even when every parameter matches.
    * ``"params"`` — one member per ``type(m).model_fields`` name, valued ``getattr(m, name)``
      through :func:`coerce`, omitting members whose raw value is ``None`` (§3.6's null rule)
      or a ``SecretStr`` (the secret exclusion).
    * ``"bound"`` — the merged kwargs overlay of ``bindings``, present only when it has a
      member left after the same rules. **Outermost binding wins** on a key collision, which is
      the invoke-time direction: an outer binding passes its kwargs *into* the inner one's
      call, where they override. A ``with_config``-only wrapper therefore contributes nothing —
      its kwargs are empty and (c) excludes ``RunnableConfig`` content from the 1.0 digest
      input — so wrapping a model in one does not move its ``config_digest``.

    The recorded asymmetry (c) blesses, worth knowing when reading a digest: the base-model
    observability fields (``callbacks``, ``tags``, ``metadata``, ``verbose``, ``cache``,
    ``rate_limiter``, ``custom_get_token_ids``) are ``model_fields`` members, so they digest
    when set **at construction** while identical content passed through ``with_config`` does
    not. (c) says "their defaults are ``None``, so the common case digests nothing either way";
    at the pinned substrate ``verbose`` is the exception — it defaults through a factory
    reading a process-global — and ``metadata`` is filled with the running langchain-core
    version. Both are inside (c)'s blessing and both are VERSION-COMPAT drift-probe surfaces.

    The field names come off the mapping through the unbound accessor, like every other
    container read here, so a ``model_fields`` that is a ``dict`` *subclass* cannot answer the
    iteration with code of its own.
    """
    fields = getattr(type(model), "model_fields", None)
    names = tuple(dict.keys(fields)) if isinstance(fields, dict) else ()
    params: dict[str, Json] = {}
    for name in names:
        try:
            value = getattr(model, name)
        except AttributeError:
            # (e)'s recorded implementer edge: a `model_fields` name absent from the instance's
            # `__dict__`, reachable only through `model_construct()`. It degrades to the
            # absent-digest path rather than raising — and it is the only way `config_digest`
            # is not Full on a discovered model node.
            return None
        if _omitted(value):
            continue
        params[name] = coerce(value)
    form: dict[str, Json] = {"provider": type_identity(model), "params": params}
    overlay = _bound_overlay(bindings)
    if overlay is not None:
        form["bound"] = overlay
    return form


def _bound_overlay(bindings: Sequence[object]) -> Json | None:
    """(c)'s ``"bound"`` member value, or ``None`` when the member is absent.

    ``bindings`` arrives outermost first, so the merge runs inward-out — the innermost
    binding's kwargs are laid down first and each enclosing one overwrites — and the result is
    the mapping an invocation would actually pass. The member rules then apply to the merged
    overlay, so an outer binding that sets a key to ``None`` genuinely removes it.

    Only an exact ``RunnableBinding`` **or one of the enumerated stock subclasses**
    (:mod:`gebra.extraction.stock`; ``_ChatModelBinding`` at the pin) contributes — (a) as
    amended by DEC-21. Any other subclass could answer ``kwargs`` with code of its own, which is
    the exact-type gate §5's stitching uses on the composition members (PD-025 / DEC-20), and a
    ``RunnableRetry`` — a sibling under ``RunnableBindingBase``, and no ``RunnableBinding``
    subclass at all — holds retry settings rather than the generation-config overlay (c) names.

    **What a tool overlay digests as, stated because it is a limit.** ``model.bind(tools=…)``
    puts whatever was bound into ``kwargs["tools"]``, and (d)'s coercion K applies to it like
    any other value: the mainstream shape — the JSON-schema ``dict``s a provider's
    ``bind_tools`` converts to — digests in full, member by member, so editing a tool's name,
    description or parameter schema moves ``config_digest``. A tool passed as a **``BaseTool``
    object** is not JSON data and takes K rule 12, so it digests as its class identity: the tool
    *set*'s shape still moves the digest, but swapping one ``StructuredTool`` for another with a
    different body does not. That is K applied as ratified, not a choice made here; widening it
    would mean projecting a tool's own surface, which is a §7.4 (b)-shaped vocabulary extension
    and therefore a future DEC. Recorded in PD-043 and tested both ways.

    **(d) rule 9 applies in full here, not by halves.** (c) says the overlay takes "the same
    member rules", and the overlay is a mapping like any other in the digest input: a key with
    no member name, or two keys of one binding rendering to one name, takes the *whole* overlay
    to the marker rather than to a half-read object — the same disposition ``_coerce_mapping``
    gives every other mapping, and for the same reason (b) refuses a partial digest. A key
    present in two *different* bindings is not a collision but the outermost-wins rule.
    """
    merged: dict[str, object] = {}
    for binding in reversed(tuple(bindings)):
        if not is_binding(type(binding)):
            # `continue` rather than `break`, and the difference is unreachable today: `bindings`
            # is built by :func:`gebra.extraction.lcel._emit_frame`, which resets the chain at any
            # non-bind frame (PD-028 D7's contiguity), so a non-admitted object never appears in
            # one. If a second producer ever builds a chain another way — §5 discovery inside a
            # builder node is the candidate (PD-028 D10) — this must become a `break`, or an
            # outer overlay separated from the model by something else would merge, which D7
            # rules out.
            continue
        kwargs = getattr(binding, "kwargs", None)
        if not isinstance(kwargs, dict):
            continue
        named: set[str] = set()
        for key, value in dict.items(kwargs):
            name = _key_name(key)
            if name is None or name in named:
                return _marker("mapping:key")
            named.add(name)
            merged[name] = value
    overlay = {name: coerce(value) for name, value in merged.items() if not _omitted(value)}
    return overlay or None


def _omitted(value: object) -> bool:
    """Whether (c)'s two member rules drop this member, keyed on its **raw** value.

    ``None`` is the §3.6 null rule, which the shipped pipeline would apply anyway; ``SecretStr``
    is the secret exclusion, read as a *type* and never for its content — there is no
    ``get_secret_value()`` call anywhere on this path.
    """
    return value is None or isinstance(value, SecretStr)


def _config_digest(node_id: str, model: object, bindings: Sequence[object]) -> NodeDigests:
    """``config_digest`` for one carrier: C through §3.6's pipeline, or (e)'s record."""
    form = config_form(model, bindings)
    if form is None:
        return NodeDigests(
            warnings=(
                _unsupported(
                    node_id,
                    _MODEL_FIELD_UNREADABLE,
                    (
                        f"a declared model field of {type_identity(model)} is absent from the "
                        "instance itself, so the config surface INTROSPECTION-SPEC §7.4 (c) "
                        "names cannot be read in full and this node's config_digest is absent "
                        "rather than computed over part of it"
                    ),
                    {"offender": type_identity(model)},
                ),
            )
        )
    return NodeDigests(config=render_digest(canonical_foreign_bytes(form)))


# ── (d) the coercion K ───────────────────────────────────────────────────────────────────


def coerce(value: object) -> Json:
    """K of §7.4 (d): any Python value as JSON data the §3.6 pipeline carries.

    Total, deterministic, and first-match-wins over the twelve rows:

    ===  =========================  ===================================================
    #    Value                      Result
    ===  =========================  ===================================================
    1    ``None``                   ``null`` (a *member* is then omitted; an item kept)
    2    ``bool``                   itself
    3    ``SecretStr``              the ``"secret"`` marker (a member is omitted instead)
    4    ``Enum``                   ``K(value)``
    5    ``int``                    itself within ±(2⁵³−1), else the range marker
    6    ``float``                  itself if finite, else the non-finite marker
    7    ``str``                    itself; a lone surrogate → its marker
    8    ``bytes``/``bytearray``    the ``"bytes"`` marker
    9    ``dict``                   an object; an unusable key sends the *whole mapping*
    10   ``list``/``tuple``         an array, authored order
    11   ``set``/``frozenset``      an array, sorted by each coerced member's JCS bytes
    12   anything else              the class-identity marker
    ===  =========================  ===================================================

    **Why a marker rather than a drop or an exception.** Dropping is silent insensitivity — a
    config edit swapping one unrepresentable value for another would not move the digest,
    recreating the gap the slot exists to close — and raising breaks extraction totality for the
    *common* case, since every provider model object holds plumbing values. The marker is the
    honest, deterministic record: it carries the class identity, so a swapped client class still
    moves the digest, and it carries nothing else, so no address and no foreign ``__repr__``
    ever reaches the bytes. Marker substitution is **silent by specification** (§7.4 (d));
    warnings accompany only absent digests.

    **Cycles.** A visited set keyed by object identity on the current walk path — the §2
    termination rule — so a config that holds itself coerces its re-entry to the ``"cycle"``
    marker instead of recursing. The check is on the *path*, not on everything seen: a value
    that legitimately appears twice as siblings coerces twice, identically.
    """
    return _coerce(value, ())


def _coerce(value: object, path: tuple[int, ...]) -> Json:
    """K, with the current walk path for (d)'s cycle rule."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, SecretStr):
        return _marker("secret")
    if isinstance(value, enum.Enum):
        return _coerce(_ENUM_VALUE(value), path)
    if isinstance(value, int):
        number = int.__index__(value)
        if not I_JSON_MIN_INT <= number <= I_JSON_MAX_INT:
            # PD-004: the value is never embedded and never stringified — the marker records
            # that an out-of-range integer was here, not which one.
            return _marker("int:i-json-range")
        return number
    if isinstance(value, float):
        real = float.__float__(value)
        return real if math.isfinite(real) else _marker("float:non-finite")
    if isinstance(value, str):
        text = str.__str__(value)
        return text if _encodable(text) else _marker("str:lone-surrogate")
    if isinstance(value, (bytes, bytearray)):
        return _marker("bytes")
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        # (d) rules 9–11, behind the one cycle check the §2 termination rule asks for. Each
        # container is read through its own unbound built-in accessor, so a subclass that
        # overrode ``items``/``__iter__`` never gets to answer.
        if id(value) in path:
            return _marker("cycle")
        inner = (*path, id(value))
        if isinstance(value, dict):
            return _coerce_mapping(value, inner)
        if isinstance(value, (list, tuple)):
            items = list.__iter__(value) if isinstance(value, list) else tuple.__iter__(value)
            return [_coerce(item, inner) for item in items]
        return _coerce_members(value, inner)
    return _marker(type_identity(value))


def _coerce_members(value: set[Any] | frozenset[Any], path: tuple[int, ...]) -> Json:
    """(d) rule 11: a set as an array, ordered by each coerced member's own JCS bytes.

    A set has no authored order and its iteration order varies with the process's string-hash
    seed, so an array in iteration order would put a run-dependent sequence inside a digest.
    Ordering by canonical bytes is the device IR-SPEC §6.2 already uses for ``edges[]``: total
    and implementation-independent. Sorting the *coerced* members never compares the source
    objects, so no foreign ``__lt__`` runs; a tie is a genuine duplicate under the projection,
    and the sort is stable, so either arrival order gives one array.
    """
    members = set.__iter__(value) if isinstance(value, set) else frozenset.__iter__(value)
    coerced = [_coerce(member, path) for member in members]
    keyed = [(canonical_foreign_bytes(item), item) for item in coerced]
    keyed.sort(key=lambda pair: pair[0])
    return [item for _, item in keyed]


def _coerce_mapping(value: dict[Any, Any], path: tuple[int, ...]) -> Json:
    """(d) rule 9: an object, or the ``"mapping:key"`` marker for the whole mapping.

    A key of exact type ``str`` names its member verbatim; a key of exact type ``bool``, ``int``
    or ``float`` names it by that scalar's own JCS rendering, which is what carries an
    integer-keyed ``logit_bias`` map into the digest. Anything else — a key type with no
    specified spelling, a key whose rendering is refused, or two keys that render to one name —
    takes the **whole mapping** to a marker rather than a partial object, for the reason (b)
    refuses a partial digest.

    Rule 3's member half rides here too: a ``SecretStr`` in member position is omitted rather
    than marked, wherever in the walk the mapping sits.
    """
    members: dict[str, Json] = {}
    named: set[str] = set()
    for key, member in dict.items(value):
        name = _key_name(key)
        if name is None or name in named:
            return _marker("mapping:key")
        named.add(name)
        if _omitted(member):
            continue
        members[name] = _coerce(member, path)
    return members


def _key_name(key: object) -> str | None:
    """A mapping key's member name under (d) rule 9, or ``None`` when it has none.

    ``bool`` is listed before ``int`` for the reason JSON has both: ``True`` renders as
    ``"true"``, not as ``"1"``. The scalar renderings come from the shipped JCS emitter — the
    same ES number formatting the digest itself uses — so ``{1: …}`` and ``{1.0: …}`` render to
    one name, and the caller's collision check is what sends that mapping to the marker.

    Nothing here hashes or compares the key **or its class**: identity tests on the type and an
    unbound accessor on the value, so a key object's ``__hash__``/``__eq__``/``__str__`` and its
    metaclass's ``__hash__``/``__eq__`` are all left alone (§1 rule 3).
    """
    holder = type(key)
    if holder is str:
        text = str.__str__(key)
        return text if _encodable(text) else None
    if _one_of(holder, (bool, int, float)):
        try:
            return canonical_foreign_bytes(key).decode("ascii")
        except CanonicalizationError:
            return None
    return None


def _encodable(text: str) -> bool:
    """Whether ``text`` has a UTF-8 encoding at all — a lone surrogate has none (§6.1 step 6)."""
    try:
        str.encode(text, "utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _marker(what: str) -> dict[str, Json]:
    """One unrepresentable-value marker — the deterministic stand-in of (d)."""
    return {UNREPRESENTABLE: what}


# ── §8 records ───────────────────────────────────────────────────────────────────────────


def _unsupported(
    node_id: str, construct: str, why: str, location: Mapping[str, Any]
) -> ExtractionWarning:
    """One ``unsupported-construct``, carrying its §8 row's four facts plus §7.4's fifth.

    §8's row for the §7.4 case adds "the offender's class identity (and item index)" to the
    generic four, and both ride in ``detail`` rather than being read out of the message, per §4's
    "structured fields, never a bare string".
    """
    return ExtractionWarning(
        code=ExtractionWarningCode.UNSUPPORTED_CONSTRUCT,
        message=f"{construct}: {why}",
        node=node_id,
        detail={
            "construct": construct,
            "location": {"node": node_id, **location},
            "why": why,
            "ir_partial": True,
        },
    )
