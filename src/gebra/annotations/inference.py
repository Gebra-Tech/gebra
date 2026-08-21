"""Shallow contract inference — ANNOTATION-API-SPEC §4 (ratified — DEC-08).

The lowest tier of §3's precedence chain, and the only one that reads no declaration: what a
node's own source makes statically evident. DEC-08 fixed its depth in one word — **shallow**
— and §4 turns that into a closed table of five licensed patterns over two slots. Nothing
outside that table is inferred, and two slots is the whole reach:

===========  ===================================================================
``input``    (a) a state-parameter annotation that is a ``TypedDict``/pydantic
             **projection** — its declared keys; (b) a literal subscript or
             attribute read of the state parameter in the node's own body.
``output``   (a) a literal dict display returned; (b) a ``TypedDict`` return
             annotation — its keys; (c) a literal ``Command(update={...})``
             construction in the node body.
===========  ===================================================================

Four properties carry the module, and each is enforced rather than described.

**NEVER-SILENT-UPGRADE, structurally.** §4: inference "**never** yields ``idempotent``,
``deterministic``, ``variant``, or ``compensation``" — those slots unlock retry, memoisation,
termination-witness and compensation reasoning that "must be opted into by an explicit
declaration" — and §1 adds ``args_schema`` ("never inferred — the §4 closed pattern table has
no pattern for it"). So the contract this module returns is built at exactly one place, from
four literal keywords (:func:`_contribution`). A fifth slot cannot be set by a code path that
does not exist, which is a stronger statement than a test, and the test is there as well.

**Nothing is evaluated.** §4: inference "consumes exactly the node callable's own AST and the
graph state schema — nothing else — in a single pass … no imports are followed and no code is
evaluated (never-invokes, decision D-018)". This module therefore never calls
:func:`typing.get_type_hints`, which §6 licenses for the *router-classification* read and
which would ``eval`` a string annotation in its module's namespace. A ``str`` annotation —
what ``from __future__ import annotations`` leaves behind — is simply not a licensed pattern
match, recorded as :attr:`Blocker.STRING_ANNOTATION`. The annotation *objects* the patterns
do read come off the function's own ``__annotations__``, where the interpreter put them at
``def`` time; reading them evaluates nothing.

**The source is read, not fetched.** :func:`read_node_source` locates the definition itself —
``__code__.co_filename`` and ``co_firstlineno``, the file's bytes, :func:`ast.parse` — rather
than through :func:`inspect.getsource`. The difference is WA-07: ``inspect`` routes through
:mod:`linecache`, which for a file that is not on disk calls the module's own
``__loader__.get_source()`` — user code — and through :func:`inspect.getmodule`, which sweeps
``sys.modules`` reading ``__file__`` attributes that a PEP-562 module ``__getattr__`` can
intercept. Neither is reachable from here.

**Conservative where it cannot see.** D-011's floor is restated by §4: a node that writes
state resolves to ``effect: [write]``, a node with no write evidence to ``pure: true``, and
both are warned. The second is "a no-evidence-found result, not a proof" — so a body this
module could not read at all takes the ``effect: [write]`` floor, never ``pure``: D-011's own
words are "``pure`` for **provably** read-only", and an unread body proves nothing.

**What this module does not do.** It does not resolve anything into an IR and it does not
rank itself against the other tiers. §3's per-slot chain (Decorator > Tool-carried > Sidecar >
Inference), its conflict warnings and the resolved-contract validation are a later card. The
one part of §3 that lives here is the sentence inference cannot be written without —
"Inference (lowest) … fills what remains": :func:`infer` is told which slots the higher tiers
already filled and contributes to none of them, because a ``contract-inferred`` warning naming
a *declared* slot would make §5's grade lookup call that slot heuristic-grade.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07). It reads one
file — the one that defines the node — and parses it as an AST; no value in it is called, and
:func:`ast.parse` compiles nothing that can run. **Four residuals, stated rather than
implied**, in the voice :mod:`gebra.annotations.contract` uses for its own, because "executes
nothing" would be too strong for a surface that reads objects the caller built:

* recognizing a pydantic projection reads ``model_fields`` off the annotation class, and that
  is a metaclass property. There is no way to learn a model's field names without asking the
  model; a class that answers by raising is read as "no projection" rather than allowed to
  abort the extraction.
* the state schema and annotation objects arrive from the caller. They are compared by
  identity and their declared keys are read through unbound built-in accessors, so a hostile
  ``__eq__`` or metaclass ``__getattr__`` is not consulted — but ``issubclass`` consults
  pydantic's own ``__subclasscheck__``, and a metaclass-level ``__dict__`` property would be a
  data descriptor that ``getattr`` runs.
* :func:`ast.parse` is given **bytes**, so the file's own PEP 263 coding cookie decides how it
  is decoded — the same decision the interpreter made when it imported the module. A cookie
  naming a codec that is not yet loaded reaches :func:`codecs.lookup`, which consults
  registered search functions and imports an ``encodings`` submodule. Reachable only for a
  file this module was pointed at but the interpreter never imported; the alternative,
  decoding as UTF-8 regardless, would silently misread a legally-encoded module. The tripwire
  arms it: nothing may load a module that was not already imported.
* the walk descends recursively, and a body nested past the interpreter's stack is caught and
  read as "no body" (the D-011 floor) rather than raised.

**One question this module does not answer, recorded for the card that fills a slot.** §4's
keys come out of arbitrary source text, and IR-SPEC §6.3 makes ``input``/``output`` entries
identifier-role — NFC, no lone surrogates. A node reading ``state["café"]`` spelled decomposed
would make ``graph_version()`` unobtainable for the whole document once §3 resolves the slot.
Whether a heuristic-grade key may be *dropped* rather than break a digest is a spec question
(IR-SPEC §6.3 ⊗ ANNOTATION §4), not an implementation choice, so this module emits what the
source says and the question travels with the resolution card.
"""

from __future__ import annotations

import ast
import types
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, TypeAlias

from pydantic import BaseModel

from gebra.annotations.contract import NodeContract
from gebra.annotations.slots import ANNOTATION_SLOTS, AnnotationSlot, SlotGrade
from gebra.naming import type_identity

__all__ = [
    "DEFAULT_EFFECT",
    "HEURISTIC_GRADES",
    "INFERENCE_SLOTS",
    "MUTATING_METHODS",
    "NEVER_INFERRED",
    "Blocker",
    "DefaultRule",
    "Inference",
    "InferenceFinding",
    "InferredKey",
    "NodeSource",
    "Pattern",
    "SourceCache",
    "SourceRule",
    "StateSchema",
    "infer",
    "infer_node",
    "read_node_source",
]

#: The two slots §4's pattern table licenses, plus the two the D-011 defaults fill. Nothing
#: else is reachable: :func:`_contribution` names exactly these four and there is no other
#: construction site.
INFERENCE_SLOTS: Final[tuple[AnnotationSlot, ...]] = ("input", "output", "effect", "pure")

#: The slots inference **never** yields, written out from the specs rather than derived from
#: :data:`INFERENCE_SLOTS`, so that a test can assert the two partition
#: :data:`~gebra.annotations.slots.ANNOTATION_SLOTS` instead of restating the code.
#:
#: The first four are §4's NEVER-SILENT-UPGRADE rule (DEC-08): they "unlock retry,
#: memoisation, termination-witness, and compensation reasoning (P-02, P-06–P-08) that must be
#: opted into by an explicit declaration". ``args_schema`` is §1's own sentence — "never
#: inferred — the §4 closed pattern table has no pattern for it".
NEVER_INFERRED: Final[tuple[AnnotationSlot, ...]] = (
    "idempotent",
    "deterministic",
    "variant",
    "compensation",
    "args_schema",
)

#: The decision D-011 conservative floor for a node that writes state (§4). One tag, from the
#: closed D-011 vocabulary — "a conservative floor, not a claim" (§5).
DEFAULT_EFFECT: Final[tuple[str, ...]] = ("write",)

#: The two §4 grades a finding can carry. §5's third, :attr:`SlotGrade.DECLARED`, is what the
#: *absence* of a finding means, so :class:`InferenceFinding` refuses it.
HEURISTIC_GRADES: Final[tuple[SlotGrade, ...]] = (SlotGrade.INFERRED, SlotGrade.DEFAULTED)

#: Method names that mutate the object they are called on, closed over the built-in container
#: types a LangGraph state (or a value inside one) actually has: ``dict``, ``list`` and
#: ``set``. A call to one of these on an expression rooted at the state parameter is the
#: "mutation of the state parameter" half of §4's write-evidence test — the half that is not a
#: licensed output pattern. Every other method call on the state parameter is left alone:
#: ``state.get("k")`` and ``state.keys()`` read, and reading is not writing.
MUTATING_METHODS: Final[frozenset[str]] = frozenset(
    {
        "update",
        "setdefault",
        "pop",
        "popitem",
        "clear",
        "append",
        "extend",
        "insert",
        "remove",
        "sort",
        "reverse",
        "add",
        "discard",
        "difference_update",
        "intersection_update",
        "symmetric_difference_update",
        "__setitem__",
        "__delitem__",
    }
)

#: The name a literal fan-out/update construction is written under (§4 output pattern (c)).
_COMMAND: Final = "Command"

#: How large a defining module this reader will parse, in bytes. A bound rather than a policy:
#: it exists so that a ``co_filename`` naming something enormous degrades to the D-011 floor
#: instead of reading it, and it sits far above any module a person writes.
_MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

#: How many parsed modules one :class:`SourceCache` holds before it starts over.
_MAX_CACHED_MODULES: Final = 256


class Pattern(str, Enum):
    """The §4 licensed pattern that put one key in a slot — the citation §4 requires.

    §4: inference emits "one licensed-pattern citation per emitted key (carried by that node's
    ``contract-inferred`` warning)", and INTROSPECTION §8's row names the same four spellings
    ("annotation keys / literal state access / literal return / ``Command(update=...)``").
    The table is closed: a key with no citation here is a key this module cannot emit.
    """

    STATE_ANNOTATION_KEYS = "state-annotation-keys"
    """``input`` (a) — the declared keys of a projection annotation on the state parameter."""

    STATE_ACCESS = "state-access"
    """``input`` (b) — a literal ``state["k"]`` / ``state.k`` read in the node's own body."""

    RETURN_LITERAL = "return-literal"
    """``output`` (a) — a literal dict display in a ``return`` statement."""

    RETURN_ANNOTATION_KEYS = "return-annotation-keys"
    """``output`` (b) — the declared keys of a ``TypedDict`` return annotation."""

    COMMAND_UPDATE = "command-update"
    """``output`` (c) — a literal ``Command(update={...})`` construction in the body."""


class SourceRule(str, Enum):
    """Whether a node's own AST could be read, and if not, why (§4's first argument).

    Every member other than :attr:`READ` sends the node to the D-011 floor: §4's defaults are
    what a node "outside the patterns" falls to, and a body that could not be read is outside
    every pattern. The distinction is kept because it is the "why no pattern applied" field
    the ``contract-defaulted`` registry row asks for.
    """

    READ = "read"
    """The definition was located and parsed."""

    NOT_A_PYTHON_FUNCTION = "not-a-python-function"
    """The node is not a Python function or bound method — a callable object, a
    ``functools.partial``, a built-in, a ``Runnable``. Following it inward to something that
    *is* one is §6's wrapper walk, which belongs to the resolution card, not to §4."""

    OPAQUE = "opaque"
    """The caller declared the node opaque — §4: "opaque nodes (``RunnableLambda`` bodies …)
    skip inference entirely and go straight to defaults"."""

    SOURCE_UNAVAILABLE = "source-unavailable"
    """No readable source file: a definition compiled from a string or a REPL, a file that is
    gone, unreadable, not a regular file, or past :data:`_MAX_SOURCE_BYTES`."""

    SOURCE_UNPARSABLE = "source-unparsable"
    """The file exists but is not parsable Python — it changed since it was imported, or it
    is a compiled artifact whose ``co_filename`` points at something else."""

    DEFINITION_NOT_FOUND = "definition-not-found"
    """The file parsed, but no definition in it matches the code object's name and line."""

    DEFINITION_AMBIGUOUS = "definition-ambiguous"
    """Several definitions match — two ``lambda``\\ s on one line, and nothing in the code
    object separates them. Refused rather than guessed: the wrong body is worse than none."""


class DefaultRule(str, Enum):
    """Which decision D-011 conservative default applied, and on what evidence (§4).

    §4 states two, and the third is what its own wording leaves for the case where the body
    could not be examined at all — see :attr:`BODY_UNAVAILABLE`.
    """

    WRITES_STATE = "writes-state"
    """"An unannotated node that writes state resolves to ``effect: [write]``" (§4)."""

    NO_WRITE_EVIDENCE = "no-write-evidence"
    """"A node with **no write evidence under the closed §4 patterns** … resolves to
    ``pure: true``" — "a no-evidence-found result, not a proof" (§4)."""

    BODY_UNAVAILABLE = "body-unavailable"
    """The body was never examined, so the floor applies: ``effect: [write]``.

    §4's second bullet requires that "no licensed output pattern matches **and** no
    assignment/mutation of the state parameter appears in the node body" — a test on what the
    body shows. An unread body shows neither, and D-011's own words are "``pure`` for
    **provably** read-only" (INTROSPECTION §5 rule 5 repeats them for the opaque case), so
    reading the absence of evidence as evidence of absence is the one thing this rule is
    there to prevent."""


#: The default rules whose applied value is the :data:`DEFAULT_EFFECT` floor — two of the
#: three, since the third *is* the ``pure`` case.
_EFFECT_DEFAULTS: Final[frozenset[DefaultRule]] = frozenset(
    {DefaultRule.WRITES_STATE, DefaultRule.BODY_UNAVAILABLE}
)


class Blocker(str, Enum):
    """Why a §4 pattern did not apply — the "why no pattern applied" field of the registry.

    Closed, and deliberately specific: a node that fell to the defaults because its state
    parameter is annotated with the graph's own state schema has a different repair (annotate
    a projection, or declare the contract) from one whose returns are built by a helper.
    """

    NO_STATE_PARAMETER = "no-state-parameter"
    """The callable declares no positional parameter, so §4's state parameter does not
    exist and neither input pattern has a subject."""

    NO_ANNOTATION = "no-annotation"
    """The state parameter (or the return) carries no annotation."""

    STRING_ANNOTATION = "string-annotation"
    """The annotation is a string — ``from __future__ import annotations``, or an explicit
    forward reference. Resolving it means evaluating it, which §4 forbids."""

    STATE_SCHEMA_UNKNOWN = "state-schema-unknown"
    """No graph state schema was supplied, so the §4 full-state exclusion cannot be
    checked — and applying pattern (a) without it is exactly the case the exclusion is
    about."""

    FULL_STATE_ANNOTATION = "full-state-annotation"
    """§4's full-state-annotation exclusion: the annotation *is* the graph's state schema, so
    it "carries no selective read/write information"."""

    NOT_A_PROJECTION = "not-a-projection"
    """The annotation is neither a ``TypedDict`` nor a pydantic model, so it declares no
    keys to read."""

    NOT_A_TYPED_DICT = "not-a-typed-dict"
    """The **return** annotation is a pydantic model. §4's table licenses a
    ``TypedDict``/pydantic projection on the state parameter and a ``TypedDict`` return
    annotation, and the table is closed — so this projection is one gebra may not read here."""

    PROJECTION_UNREADABLE = "projection-unreadable"
    """The annotation is a pydantic model that would not say what fields it declares."""

    STATE_PARAMETER_REBOUND = "state-parameter-rebound"
    """The body assigns to the state parameter's own name, so a later ``state["k"]`` is a
    read of something else. Pattern (b) is dropped rather than attributed to the state."""

    RETURN_NOT_LITERAL = "return-not-literal"
    """§4's multi-return rule: a ``return`` site that is not a licensed literal. "If **any**
    site is unlicensed (non-literal), output inference is abandoned wholesale"."""

    COMMAND_UPDATE_NOT_LITERAL = "command-update-not-literal"
    """A ``Command`` whose ``update=`` is not a literal dict display — the same abandonment
    as an unlicensed return, for the same reason: a partial union would under-report."""

    NO_LICENSED_PATTERN = "no-licensed-pattern"
    """The body was read and nothing in the closed table matched."""

    BODY_UNAVAILABLE = "body-unavailable"
    """The node's own AST could not be read at all; :attr:`NodeSource.rule` says why."""

    BODY_TOO_DEEP = "body-too-deep"
    """The body parsed and then nested deeper than the walk could descend. Same outcome as an
    unreadable body — the D-011 floor — rather than a :class:`RecursionError` out of an
    extraction."""


@dataclass(frozen=True)
class StateSchema:
    """The graph's own state schema — the second argument of §4's ``infer``.

    Its one job here is §4's **full-state-annotation exclusion**: "when the state-parameter
    (or return-type) annotation is the graph's full state schema itself, the annotation
    carries no selective read/write information — the default LangGraph idiom
    ``def node(state: State) -> State`` infers **nothing** from its annotations". So what the
    engine needs is the identity of the objects that *are* the graph's schema, which is why
    this holds objects and not keys.

    It holds a *sequence* because a caller may have more than one object to name — a graph can
    declare an input and an output schema beside its state schema. **Which** of them count as
    "the graph's full state schema itself" is not decided here: §4 names one, this compares
    against whatever it is handed, and the choice belongs to the card that reads the schemas
    off a builder.

    Comparison is ``is``: the exclusion asks whether the annotation is that schema, and a
    schema class's own ``__eq__`` is not consulted.
    """

    schemas: tuple[object, ...] = ()

    @classmethod
    def of(cls, *schemas: object) -> StateSchema:
        """The graph's schema objects, in declaration order."""
        return cls(schemas=schemas)

    def is_full_state(self, annotation: object) -> bool:
        """Whether ``annotation`` is one of the graph's own schemas (the §4 exclusion)."""
        return any(annotation is schema for schema in self.schemas)


@dataclass(frozen=True)
class InferredKey:
    """One inferred state key with the §4 pattern that licensed it.

    Attributes:
        key: The state key, exactly as the source spells it.
        pattern: The licensed pattern — §4 requires "one licensed-pattern citation per
            emitted key", which is what makes an inferred slot explainable in one line.
    """

    key: str
    pattern: Pattern


@dataclass(frozen=True)
class NodeSource:
    """A node callable's own AST, or the reason there is none (§4's first argument).

    Total: :func:`read_node_source` has no failure mode, because every way of not having a
    body is a node that falls to the D-011 defaults rather than an extraction that stops.

    Attributes:
        rule: Whether the definition was read, and if not, why.
        definition: The located ``def``/``async def``/``lambda`` node, or ``None``.
        annotations: The callable's own ``__annotations__``, as the interpreter recorded them
            at ``def`` time. Values are whatever was written — a class, a typing form, or a
            ``str`` under ``from __future__ import annotations``, which §4's no-evaluation
            rule leaves unresolved.
        bound: Whether the callable is a bound method, whose first AST parameter is the
            ``self``/``cls`` §4 says to look past.
        detail: Where the reader got to — the file, the line, the code object's name — as
            JSON data, so it can ride a warning's ``detail``.
    """

    rule: SourceRule
    definition: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | None = None
    annotations: Mapping[str, object] = field(default_factory=dict)
    bound: bool = False
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def read(self) -> bool:
        """Whether there is a body to apply the patterns to."""
        return self.definition is not None


@dataclass(frozen=True)
class InferenceFinding:
    """One §4 outcome for one node, in the shape the §4 warning registry asks for.

    A neutral record rather than an :class:`~gebra.extraction.warnings.ExtractionWarning`
    because this package must not import :mod:`gebra.extraction` — that package reads the
    substrate's classes, and the dependency between the two runs one way only.
    :mod:`gebra.extraction.inference` is what turns these into ``contract-inferred`` /
    ``contract-defaulted`` records; the fields here are already the fields §4 names, so that
    conversion adds a code and the node id and nothing else.

    Attributes:
        grade: :attr:`SlotGrade.INFERRED` for a pattern match, :attr:`SlotGrade.DEFAULTED` for
            a D-011 default — §5's two heuristic grades, which are also the two warning codes.
        slots: The slots this finding accounts for. Never empty: both registry rows are read
            through §5's (node id, slot) lookup, so a finding that named no slot would be a
            warning no validator could act on.
        message: A one-line human summary. Display-only, like every warning message in this
            build: the facts are the fields.
        detail: The rest of the row's "carries" column as JSON data.

    Raises:
        ValueError: if built with :attr:`SlotGrade.DECLARED` (which is the absence of a
            finding, never one of them) or with no slots.
    """

    grade: SlotGrade
    slots: tuple[AnnotationSlot, ...]
    message: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.grade not in HEURISTIC_GRADES:
            raise ValueError(
                f"{self.grade.value!r} is not one of the two grades §4 produces "
                f"({', '.join(grade.value for grade in HEURISTIC_GRADES)}); declared-grade is "
                "what the absence of a finding means (ANNOTATION-API-SPEC §5)"
            )
        if not self.slots:
            raise ValueError(
                "an inference finding names the slot(s) it accounts for: §5's grade lookup is "
                "keyed by the (node id, slot) pair"
            )


@dataclass(frozen=True)
class Inference:
    """What §4 contributes for one node — the tier's whole output.

    Attributes:
        contract: The contribution, in the same carrier the decorator (§1) and the sidecar
            (§2) produce, so §3's chain compares three tiers of one type. At most the four
            slots of :data:`INFERENCE_SLOTS` are set, and a slot the higher tiers already
            filled is never among them.
        keys: The per-key citations (§4) for whichever of ``input``/``output`` were inferred.
        default: Which D-011 default applied, or ``None`` when the pair was already declared.
        blockers: Why the patterns that did not match did not match, in a stable order.
        source: Where the body came from, or why there was none.
        findings: The ``contract-inferred`` / ``contract-defaulted`` records — one per grade
            that occurred, covering every slot in :attr:`contract`.
    """

    contract: NodeContract
    source: NodeSource
    keys: Mapping[AnnotationSlot, tuple[InferredKey, ...]] = field(default_factory=dict)
    default: DefaultRule | None = None
    blockers: tuple[Blocker, ...] = ()
    findings: tuple[InferenceFinding, ...] = ()

    def inferred_slots(self) -> tuple[AnnotationSlot, ...]:
        """The slots this inference filled, in :data:`ANNOTATION_SLOTS` order."""
        return self.contract.declared_slots()


class SourceCache:
    """Parsed defining modules for one extraction — an explicit, caller-owned cache.

    §4 bounds *inference* at "O(|node-body AST|) per node"; parsing the module a node is
    defined in is the I/O around that, and a graph's nodes usually share a handful of files.
    A caller that infers over many nodes passes one of these; a caller that does not gets
    correctness with no shared state, which is why there is no module-level default.

    The key is the file's path together with its size and modification time, so a file that
    changes mid-extraction is re-read rather than served stale.
    """

    def __init__(self) -> None:
        self._modules: dict[tuple[str, int, int], tuple[ast.Module | None, SourceRule]] = {}

    def get(self, key: tuple[str, int, int]) -> tuple[ast.Module | None, SourceRule] | None:
        """The cached parse for ``key``, or ``None``."""
        return self._modules.get(key)

    def remember(
        self, key: tuple[str, int, int], parsed: tuple[ast.Module | None, SourceRule]
    ) -> None:
        """Cache ``parsed`` under ``key``, starting over past :data:`_MAX_CACHED_MODULES`."""
        if len(self._modules) >= _MAX_CACHED_MODULES:
            self._modules.clear()
        self._modules[key] = parsed

    def __len__(self) -> int:
        """How many parses are held."""
        return len(self._modules)


# ── Reading the node's own source ────────────────────────────────────────────────────────


def read_node_source(node: object, *, cache: SourceCache | None = None) -> NodeSource:
    """The AST of ``node``'s own definition, or the reason there is none. Never raises.

    The route is deliberate, and is the WA-07 half of this module (see the module docstring):
    the code object names its file and its first line, the file is read as bytes and parsed,
    and the definition is located by name and line. :func:`inspect.getsource` is not used —
    it can reach a module's own ``__loader__.get_source()`` through :mod:`linecache` and
    sweeps ``sys.modules`` through :func:`inspect.getmodule`, and both are user code running
    inside what is supposed to be a read.

    Args:
        node: The node callable. A plain function, an ``async def``, a ``lambda`` or a bound
            method is read; anything else is :attr:`SourceRule.NOT_A_PYTHON_FUNCTION`.
        cache: An optional per-extraction :class:`SourceCache`.

    Returns:
        A :class:`NodeSource`, whose :attr:`~NodeSource.rule` is the whole answer.
    """
    function, bound = _python_function(node)
    if function is None:
        return NodeSource(
            rule=SourceRule.NOT_A_PYTHON_FUNCTION,
            detail={"target": type_identity(node)},
        )
    code = function.__code__
    where: dict[str, Any] = {
        "file": code.co_filename,
        "line": code.co_firstlineno,
        "name": code.co_name,
    }
    tree, rule = _module_ast(code.co_filename, cache)
    if tree is None:
        return NodeSource(rule=rule, detail=where)
    definition, located = _locate(tree, code)
    if definition is None:
        return NodeSource(rule=located, detail=where)
    return NodeSource(
        rule=SourceRule.READ,
        definition=definition,
        annotations=_declared_annotations(function),
        bound=bound,
        detail=where,
    )


def _python_function(node: object) -> tuple[types.FunctionType | None, bool]:
    """``node`` as a Python function, and whether it arrived bound.

    §4: the state parameter is the first positional parameter "after ``self``/``cls`` for
    bound methods and classmethods" — and a bound classmethod is a bound method too, so one
    unwrap covers both. Nothing else is followed: a ``functools.partial``, a callable object
    or a ``Runnable`` is a wrapper, and walking wrappers is §6's rule, applied by the
    resolution card before it asks for inference.

    The test is ``type(node) is``, not ``isinstance``. Neither type can be subclassed, so the
    two admit exactly the same objects — except that ``isinstance`` falls back to reading
    ``node.__class__``, which is a property an object can answer however it likes. Everything
    below this line reads ``__code__`` and ``__annotations__`` off the result, so an object
    that talks its way past this check has its own descriptors run inside a path whose whole
    claim is that it runs nothing of the caller's (WA-07).
    """
    if type(node) is types.MethodType:
        underlying = node.__func__
        if type(underlying) is types.FunctionType:
            return underlying, True
        return None, False
    if type(node) is types.FunctionType:
        return node, False
    return None, False


def _declared_annotations(function: types.FunctionType) -> Mapping[str, object]:
    """The function's own ``__annotations__``, copied, with nothing resolved.

    The interpreter evaluated these at ``def`` time; reading them evaluates nothing. Under
    ``from __future__ import annotations`` they are strings, and they stay strings —
    :func:`typing.get_type_hints` would ``eval`` them, which §4 forbids.

    Copied through the unbound ``dict`` accessor rather than with ``dict(mapping)``: the
    ``__annotations__`` descriptor accepts any ``dict`` **subclass**, and ``dict(mapping)`` on
    one takes the generic path through its own ``keys``/``__getitem__`` — a subclass's code
    running inside a read. The pattern is :mod:`gebra.annotations.contract`'s, for its reason.
    """
    return MappingProxyType(dict(dict.items(function.__annotations__)))


def _module_ast(filename: str, cache: SourceCache | None) -> tuple[ast.Module | None, SourceRule]:
    """Parse the file ``filename``, through ``cache`` when one was given.

    A relative ``co_filename`` is resolved against the current working directory and no
    further: :mod:`linecache` searches ``sys.path`` for a matching basename, and reading a
    *different* file with the same name would infer a contract from source the node does not
    have. Not found is :attr:`SourceRule.SOURCE_UNAVAILABLE`, which is the D-011 floor.
    """
    if not filename or filename.startswith("<"):
        # `<stdin>`, `<string>`, `<ipython-input-…>`: compiled from something that is not a
        # file, so there is nothing to read (the same test `inspect` makes).
        return None, SourceRule.SOURCE_UNAVAILABLE
    try:
        path = Path(filename)
        if not path.is_file():
            # `is_file()` and not `exists()`: a FIFO would block the read forever and a
            # character device would never end it, which is the hazard the sidecar loader's
            # explicit-path gate exists for as well.
            return None, SourceRule.SOURCE_UNAVAILABLE
        stat = path.stat()
        if stat.st_size > _MAX_SOURCE_BYTES:
            return None, SourceRule.SOURCE_UNAVAILABLE
        key = (filename, stat.st_size, stat.st_mtime_ns)
        cached = None if cache is None else cache.get(key)
        if cached is not None:
            return cached
        source = path.read_bytes()
    except (OSError, ValueError):
        # `ValueError` is not a slip: a path the operating system cannot express — an embedded
        # NUL — raises it rather than `OSError`.
        return None, SourceRule.SOURCE_UNAVAILABLE
    parsed = _parse(source, filename)
    if cache is not None:
        cache.remember(key, parsed)
    return parsed


def _parse(source: bytes, filename: str) -> tuple[ast.Module | None, SourceRule]:
    """``source`` as a module AST, or why it is not one.

    Parsed from **bytes** so that the file's own PEP 263 encoding declaration decides how it
    is decoded, exactly as the interpreter decided when it imported the module.
    """
    try:
        return ast.parse(source, filename=filename), SourceRule.READ
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        # A file that is not the Python the code object came from — edited since import,
        # binary, or nested past what the parser's stack admits. All four are "no body".
        return None, SourceRule.SOURCE_UNPARSABLE


#: The AST kinds a node callable can be defined by.
_Definition: TypeAlias = "ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda"


def _locate(tree: ast.Module, code: types.CodeType) -> tuple[_Definition | None, SourceRule]:
    """The definition in ``tree`` that ``code`` came from, matched by name and line.

    A decorated function's ``co_firstlineno`` is the line of its **first decorator**, while
    the AST node's own ``lineno`` is the ``def`` — so both are candidate lines. When more than
    one definition still matches (two ``lambda``\\ s on one line), the code object's declared
    positional parameters break the tie; when they do not, the answer is
    :attr:`SourceRule.DEFINITION_AMBIGUOUS` rather than a guess.
    """
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        and _definition_name(node) == code.co_name
        and code.co_firstlineno in _definition_lines(node)
    ]
    if len(candidates) > 1:
        wanted = code.co_varnames[: code.co_argcount]
        candidates = [node for node in candidates if _positional_names(node) == wanted]
    if not candidates:
        return None, SourceRule.DEFINITION_NOT_FOUND
    if len(candidates) > 1:
        return None, SourceRule.DEFINITION_AMBIGUOUS
    return candidates[0], SourceRule.READ


def _definition_name(node: _Definition) -> str:
    """The name a code object would carry for ``node``."""
    return "<lambda>" if isinstance(node, ast.Lambda) else node.name


def _definition_lines(node: _Definition) -> frozenset[int]:
    """The lines a code object's ``co_firstlineno`` may point at for ``node``."""
    if isinstance(node, ast.Lambda):
        return frozenset({node.lineno})
    return frozenset({node.lineno, *(decorator.lineno for decorator in node.decorator_list)})


def _positional_names(node: _Definition) -> tuple[str, ...]:
    """``node``'s positional parameters, in the order a code object lists them."""
    arguments = node.args
    return tuple(argument.arg for argument in (*arguments.posonlyargs, *arguments.args))


# ── The pattern engine ───────────────────────────────────────────────────────────────────


def infer_node(
    node: object,
    *,
    state_schema: StateSchema | None = None,
    declared: Iterable[AnnotationSlot] = (),
    declared_writes: bool = False,
    opaque: bool = False,
    cache: SourceCache | None = None,
) -> Inference:
    """Read ``node``'s own source and apply §4 to it — :func:`read_node_source` then
    :func:`infer`.

    Args:
        node: The node callable.
        state_schema: The graph's state schema, for the §4 full-state exclusion.
        declared: The slots the higher §3 tiers already filled.
        declared_writes: Whether a higher tier declared a non-empty ``output`` — see
            :func:`infer`.
        opaque: Whether the node is one §4 sends "straight to defaults" without looking —
            a ``RunnableLambda`` body. Set by the caller, which is the layer that knows what
            kind of runnable the node is.
        cache: An optional per-extraction :class:`SourceCache`.
    """
    source = NodeSource(rule=SourceRule.OPAQUE) if opaque else read_node_source(node, cache=cache)
    return infer(
        source,
        state_schema=state_schema,
        declared=declared,
        declared_writes=declared_writes,
    )


def infer(
    source: NodeSource,
    *,
    state_schema: StateSchema | None = None,
    declared: Iterable[AnnotationSlot] = (),
    declared_writes: bool = False,
) -> Inference:
    """§4's ``infer(node_ast, state_schema)`` — the closed pattern table, one pass.

    Pure and per-node: it reads the given AST and the given schema and nothing else, follows
    no import, and evaluates nothing.

    Args:
        source: The node's own AST, from :func:`read_node_source`.
        state_schema: The graph's state schema. ``None`` means it is not known, which
            withdraws the two *annotation* patterns — §4's full-state exclusion cannot be
            applied without it, and applying pattern (a) blind is the case it excludes.
        declared: The slots §3's higher tiers already filled. Inference "fills what remains",
            so a slot named here gets neither a value nor a warning: a ``contract-inferred``
            record naming a declared slot would make §5's grade lookup call it
            heuristic-grade.
        declared_writes: Whether a higher §3 tier declared a non-empty ``output`` — i.e.
            whether an author has said this node writes state. It is write evidence for the
            D-011 default and nothing else: §4's two defaults are stated for "an
            **unannotated** node", and a node whose author declared its writes is not one.
            Without it, ``@gebra.contract(reads=[…], writes=["plan"])`` on a body whose writes
            happen inside a helper would resolve to ``output: ["plan"]`` *and* ``pure: true``
            — the gap-filling tier contradicting the declaration it was filling around, in the
            one direction D-011's "provably read-only" rules out.

    Returns:
        The tier's contribution and the findings that account for every slot in it.
    """
    open_slots = frozenset(INFERENCE_SLOTS) - frozenset(declared)
    blockers: list[Blocker] = []
    keys: dict[AnnotationSlot, tuple[InferredKey, ...]] = {}
    annotated_output: tuple[str, ...] = ()

    walk, unread = _walk(source)
    if walk is None:
        blockers.append(unread)
    else:
        if walk.parameter is None:
            blockers.append(Blocker.NO_STATE_PARAMETER)
        if "input" in open_slots:
            inferred = _input_keys(source, walk, state_schema, blockers)
            if inferred:
                keys["input"] = inferred
        # Asked of the node, not of the open slots: §4's D-011 precondition is "no licensed
        # output pattern **matches**", so whether the return annotation matched is a fact
        # about the node — and it is still true when the multi-return rule abandons the key
        # set it would have contributed, and when a higher tier already filled `output`.
        annotated_output = _annotation_keys(
            source.annotations.get("return", _UNANNOTATED),
            state_schema,
            blockers,
            licensed=_TYPED_DICT_ONLY,
        )
        if "output" in open_slots:
            inferred = _output_keys(annotated_output, walk)
            if inferred:
                keys["output"] = inferred
        blockers.extend(blocker for blocker in walk.blockers if blocker not in blockers)
        # Only when a pattern was actually tried: with both slots already declared, nothing
        # was looked for, and "no licensed pattern" would be a report about work not done.
        if not keys and {"input", "output"} & open_slots:
            blockers.append(Blocker.NO_LICENSED_PATTERN)

    default = _default_rule(
        walk,
        open_slots,
        matched_output=bool(annotated_output) or declared_writes,
    )
    return Inference(
        contract=_contribution(keys, default),
        source=source,
        keys=MappingProxyType(dict(keys)),
        default=default,
        blockers=tuple(blockers),
        findings=_findings(keys, default, source, tuple(blockers)),
    )


def _contribution(
    keys: Mapping[AnnotationSlot, tuple[InferredKey, ...]], default: DefaultRule | None
) -> NodeContract:
    """The four slots §4 can fill, and the only place any of them is set.

    This is the NEVER-SILENT-UPGRADE rule as code rather than as a check: the constructor
    call names ``input``, ``output``, ``effect`` and ``pure`` literally, so no reachable path
    sets ``idempotent``, ``deterministic``, ``variant``, ``compensation`` or ``args_schema``.

    An empty key set leaves its slot **unset** rather than setting it to ``[]``. An
    ``output: []`` is a positive claim ("writes nothing") that no pattern made — and IR-SPEC
    §6.3 omits empty optional arrays from the canonical form, so the claim would be invisible
    in ``graph_version`` while still blocking the D-011 floor at §3's chain.
    """
    return NodeContract(
        input=tuple(inferred.key for inferred in keys.get("input", ())) or None,
        output=tuple(inferred.key for inferred in keys.get("output", ())) or None,
        effect=DEFAULT_EFFECT if default in _EFFECT_DEFAULTS else None,
        pure=True if default is DefaultRule.NO_WRITE_EVIDENCE else None,
    )


def _default_rule(
    walk: _Walk | None, open_slots: frozenset[AnnotationSlot], *, matched_output: bool
) -> DefaultRule | None:
    """Which D-011 default applies (§4), or ``None``.

    §4's second bullet is a two-part test over the **patterns**, not over the body alone: a
    node takes the ``pure`` branch when "no licensed output pattern matches **and** no
    assignment/mutation of the state parameter appears in the node body". So a matched output
    pattern is evidence whichever of the three matched — including pattern (b), the return
    annotation, whose keys the multi-return rule may have abandoned. A node whose own return
    annotation declares what it writes is further from "provably read-only" than one this
    module could not read at all. ``matched_output`` also carries :func:`infer`'s
    ``declared_writes``, for the same reason one step up: an author's declared ``output`` is
    the strongest write evidence there is, and §4's defaults are written for "an
    **unannotated** node".

    The pair is decided together. §4 speaks of "an **unannotated** node", and ``pure`` and
    ``effect`` are one statement about a node made in two slots — D-011 declares them mutually
    exclusive — so filling one while the other is declared would assemble exactly the
    cross-surface contradiction §3's resolved-contract pass exists to repair. With either half
    declared, the tier stays out.
    """
    if not {"pure", "effect"} <= open_slots:
        return None
    if walk is None:
        return DefaultRule.BODY_UNAVAILABLE
    if walk.write_evidence or matched_output:
        return DefaultRule.WRITES_STATE
    return DefaultRule.NO_WRITE_EVIDENCE


def _walk(source: NodeSource) -> tuple[_Walk | None, Blocker]:
    """Walk the node's body once, or say why there is no walk to read.

    Total: a body deep enough to exhaust the interpreter's stack is a body this module could
    not read, which is the D-011 floor — not an exception out of an extraction. The parse
    itself is guarded in :func:`_parse`; this is the second half, because
    :class:`ast.NodeVisitor` descends recursively while :func:`ast.walk` does not.
    """
    definition = source.definition
    if definition is None:
        return None, Blocker.BODY_UNAVAILABLE
    walk = _Walk(parameter=_state_parameter(definition, bound=source.bound))
    try:
        walk.run(definition)
    except RecursionError:
        return None, Blocker.BODY_TOO_DEEP
    return walk, Blocker.BODY_UNAVAILABLE


def _state_parameter(definition: _Definition, *, bound: bool) -> str | None:
    """§4's state parameter: "the **first positional parameter** of the node callable — after
    ``self``/``cls`` for bound methods and classmethods"."""
    positional = _positional_names(definition)
    if bound:
        positional = positional[1:]
    return positional[0] if positional else None


def _input_keys(
    source: NodeSource,
    walk: _Walk,
    state_schema: StateSchema | None,
    blockers: list[Blocker],
) -> tuple[InferredKey, ...]:
    """§4's two ``input`` patterns, annotation first so its citation wins a shared key."""
    inferred: dict[str, InferredKey] = {}
    if walk.parameter is not None:
        annotated = _annotation_keys(
            source.annotations.get(walk.parameter, _UNANNOTATED),
            state_schema,
            blockers,
            licensed=_TYPED_DICT_OR_PYDANTIC,
        )
        for key in annotated:
            inferred.setdefault(key, InferredKey(key=key, pattern=Pattern.STATE_ANNOTATION_KEYS))
    if walk.rebound:
        blockers.append(Blocker.STATE_PARAMETER_REBOUND)
    else:
        for key, pattern in walk.reads.items():
            inferred.setdefault(key, InferredKey(key=key, pattern=pattern))
    return tuple(inferred.values())


def _output_keys(annotated: tuple[str, ...], walk: _Walk) -> tuple[InferredKey, ...]:
    """§4's three ``output`` patterns under the multi-return rule.

    "If **every** site matches a licensed output pattern, ``output`` is the union of their
    keys; if **any** site is unlicensed (non-literal), output inference is abandoned wholesale
    and the node falls to the defaults — a partial union would under-report writes." Wholesale
    is read as written: the return **annotation** goes with the literals, because a node whose
    writes are partly invisible is a node whose output set is not known, whichever pattern
    would have supplied part of it. That the annotation still *matched* is a separate fact, and
    it is the one the D-011 branch turns on (:func:`_default_rule`).
    """
    if walk.unlicensed_output:
        return ()
    inferred: dict[str, InferredKey] = {}
    for key in annotated:
        inferred.setdefault(key, InferredKey(key=key, pattern=Pattern.RETURN_ANNOTATION_KEYS))
    for key, pattern in walk.writes.items():
        inferred.setdefault(key, InferredKey(key=key, pattern=pattern))
    return tuple(inferred.values())


#: What "this name has no annotation" looks like, distinct from an annotation of ``None``.
_UNANNOTATED: Final = object()


#: The projection spellings §4's ``input`` row licenses: "a ``TypedDict``/pydantic projection".
_TYPED_DICT_OR_PYDANTIC: Final = True

#: The one §4's ``output`` row licenses: "a ``TypedDict`` return-type annotation — its keys".
#: The asymmetry is the spec's, stated in its table and restated in DEC-08's decision, and the
#: table is closed — "anything not on it is not inferred". A pydantic return annotation is
#: therefore :attr:`Blocker.NOT_A_TYPED_DICT`, not a projection to read: its field names would
#: otherwise land in ``output``, inside the ``graph_version`` hash scope, claiming writes no
#: pattern licenses.
_TYPED_DICT_ONLY: Final = False


def _annotation_keys(
    annotation: object,
    state_schema: StateSchema | None,
    blockers: list[Blocker],
    *,
    licensed: bool,
) -> tuple[str, ...]:
    """The declared keys of a projection annotation (§4 patterns input (a) / output (b)).

    Every way of not matching is recorded, because "why no pattern applied" is a field of the
    ``contract-defaulted`` row and each of these has a different repair.

    Args:
        annotation: The annotation object, exactly as the interpreter recorded it.
        state_schema: The graph's schema, for the full-state exclusion.
        blockers: Collected reasons, appended to.
        licensed: :data:`_TYPED_DICT_OR_PYDANTIC` on the state parameter,
            :data:`_TYPED_DICT_ONLY` on the return — §4's table is asymmetric.
    """
    if annotation is _UNANNOTATED:
        blockers.append(Blocker.NO_ANNOTATION)
        return ()
    if isinstance(annotation, str):
        # `from __future__ import annotations`, or an explicit forward reference. Resolving it
        # is evaluation, which §4 rules out; `typing.get_type_hints` is never called here.
        blockers.append(Blocker.STRING_ANNOTATION)
        return ()
    if state_schema is None:
        blockers.append(Blocker.STATE_SCHEMA_UNKNOWN)
        return ()
    if state_schema.is_full_state(annotation):
        blockers.append(Blocker.FULL_STATE_ANNOTATION)
        return ()
    keys, blocker = _projection_keys(annotation, pydantic=licensed)
    if keys is None:
        blockers.append(blocker)
        return ()
    return keys


def _projection_keys(
    annotation: object, *, pydantic: bool
) -> tuple[tuple[str, ...] | None, Blocker]:
    """``annotation``'s declared keys if it is a projection §4 licenses here, else why not.

    A ``dataclass``, an ``Annotated[...]`` form or a bare ``dict`` is not a projection at all;
    a pydantic model is one, and is licensed on the state parameter but **not** on the return
    (see :data:`_TYPED_DICT_ONLY`).
    """
    if isinstance(annotation, types.GenericAlias) or not isinstance(annotation, type):
        # The `GenericAlias` half is checked *first* and is not redundant. `dict[str, Any]` is
        # the ordinary annotation on a LangGraph node and declares no keys, and a parameterized
        # generic forwards attribute lookups it does not answer itself — ``__class__`` among
        # them on the older interpreters in the supported range — to its **origin**. That is
        # what lets `isinstance(dict[str, Any], type)` answer `True` while `issubclass` on the
        # same object raises `TypeError`. Excluding it by its own type is the answer that does
        # not depend on which interpreter is running.
        return None, Blocker.NOT_A_PROJECTION
    if issubclass(annotation, BaseModel):
        if not pydantic:
            return None, Blocker.NOT_A_TYPED_DICT
        try:
            return tuple(annotation.model_fields), Blocker.NOT_A_PROJECTION
        except Exception:  # noqa: BLE001 - see below
            # A model's field names come from the model, and asking is the only way to get
            # them: `model_fields` is a metaclass property, so a class can answer it however
            # it likes. Inference is the tier that guesses, so a class that will not say what
            # it declares is "no projection here" and the node takes the D-011 floor —
            # aborting an extraction over a heuristic read would be the "total in name only"
            # failure this posture exists to prevent.
            return None, Blocker.PROJECTION_UNREADABLE
    if not _is_typed_dict(annotation):
        return None, Blocker.NOT_A_PROJECTION
    namespace = getattr(annotation, "__dict__", None)
    if not isinstance(namespace, MappingProxyType):  # pragma: no cover - every class has one
        return None, Blocker.NOT_A_PROJECTION
    declared = MappingProxyType.get(namespace, "__annotations__")
    if not isinstance(declared, dict):  # pragma: no cover - a TypedDict always carries one
        return (), Blocker.NOT_A_PROJECTION
    return tuple(key for key in dict.keys(declared) if isinstance(key, str)), (
        Blocker.NOT_A_PROJECTION
    )


def _is_typed_dict(annotation: type) -> bool:
    """Whether ``annotation`` is a ``TypedDict`` class, whichever module declared it.

    Structural rather than ``typing.is_typeddict``: a ``TypedDict`` from
    ``typing_extensions`` — which is what a library supporting older Pythons writes, and what
    LangGraph's own examples import — is not an instance of the stdlib's private metaclass on
    every version. The three marks below are what every ``TypedDict`` class carries and no
    ordinary ``dict`` subclass does.
    """
    if not issubclass(annotation, dict):
        return False
    namespace = getattr(annotation, "__dict__", None)
    if not isinstance(namespace, MappingProxyType):  # pragma: no cover - every class has one
        return False
    return all(
        MappingProxyType.get(namespace, mark) is not None
        for mark in ("__annotations__", "__required_keys__", "__optional_keys__")
    )


# ── The body walk ────────────────────────────────────────────────────────────────────────


class _Walk(ast.NodeVisitor):
    """One pass over a node body, collecting §4's body-derived evidence.

    Scope is the node's **own** body: a nested ``def``/``lambda`` is not descended into, since
    DEC-08 rules out "helper-function dataflow … and closures" in terms. A class body *is*
    descended into — it runs where it is written — while its methods are nested definitions
    and are not.
    """

    def __init__(self, parameter: str | None) -> None:
        self.parameter = parameter
        self.reads: dict[str, Pattern] = {}
        self.writes: dict[str, Pattern] = {}
        self.write_evidence = False
        self.unlicensed_output = False
        self.rebound = False
        self.return_sites = 0
        self.blockers: list[Blocker] = []

    def run(self, definition: _Definition) -> None:
        """Walk ``definition``'s body — the statements, or a ``lambda``'s one expression."""
        if isinstance(definition, ast.Lambda):
            # §4: "A bare `lambda` used as a node has an expression body: pattern (b) applies
            # to subscript/attribute reads of its first parameter, and a dict-display body
            # counts as output pattern (a)." So the expression is the single return site.
            self._return(definition.body)
            self.visit(definition.body)
            return
        for statement in definition.body:
            self.visit(statement)

    # ── Scope ────────────────────────────────────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """A nested definition is not this node's body (DEC-08: no helper dataflow, no
        closures), so it is not descended into and its ``return``\\ s are not return sites."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """As :meth:`visit_FunctionDef`."""

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """As :meth:`visit_FunctionDef`."""

    # ── Return sites ─────────────────────────────────────────────────────────────────────

    def visit_Return(self, node: ast.Return) -> None:
        """A return site, plus whatever the returned expression itself reads."""
        self._return(node.value)
        self.generic_visit(node)

    def _return(self, value: ast.expr | None) -> None:
        """Classify one return site under §4's ``output`` patterns and multi-return rule."""
        self.return_sites += 1
        if value is None or _is_none(value):
            # `return` / `return None` writes nothing and says so in the source. Licensed
            # with no keys: the multi-return rule's own gloss for unlicensed is
            # "(non-literal)", and a constant is a literal.
            return
        if isinstance(value, ast.Dict):
            self._update(_literal_dict(value), Pattern.RETURN_LITERAL, Blocker.RETURN_NOT_LITERAL)
            return
        if isinstance(value, ast.Call) and _is_command(value):
            # Licensed; its keys — or its refusal — are recorded by `visit_Call`, since §4
            # puts pattern (c) on the construction rather than on the return.
            return
        self._abandon_output(Blocker.RETURN_NOT_LITERAL)

    def _update(self, update: _Update, pattern: Pattern, blocker: Blocker) -> None:
        """Apply one written-update reading — §4's two questions, asked separately.

        *Is a write evident?* is the D-011 defaults' test, and *are the keys readable?* is the
        multi-return rule's. They come apart exactly where a display or a ``Command`` shows a
        state update whose full key set it does not spell — ``{**base, "plan": …}`` evidences a
        write to ``plan`` while hiding whatever ``base`` carries — so the update is counted as
        evidence and the key set is abandoned, which is the conservative answer to both.
        """
        if update.evident:
            self.write_evidence = True
        if not update.complete:
            self._abandon_output(blocker)
            return
        for key in update.keys:
            self.writes.setdefault(key, pattern)

    def _abandon_output(self, blocker: Blocker) -> None:
        """§4's multi-return rule: one unlicensed site abandons ``output`` wholesale."""
        self.unlicensed_output = True
        if blocker not in self.blockers:
            self.blockers.append(blocker)

    # ── Reads, writes and mutations ──────────────────────────────────────────────────────

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """``state["k"]`` — input pattern (b) when read, write evidence when assigned."""
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            if self._rooted_at_state(node.value):
                self.write_evidence = True
        elif self._is_state(node.value):
            key = _literal_key(node)
            if key is not None:
                self.reads.setdefault(key, Pattern.STATE_ACCESS)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """``state.k`` — input pattern (b) when read, write evidence when assigned.

        A leading underscore is not read as a state key: ``state._cache`` and
        ``state.__class__`` are the object's own business, not the graph's state.
        """
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            if self._rooted_at_state(node.value):
                self.write_evidence = True
        elif self._is_state(node.value) and not node.attr.startswith("_"):
            self.reads.setdefault(node.attr, Pattern.STATE_ACCESS)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """``state["k"] += 1`` writes *and* reads, though the target's context says Store."""
        target = node.target
        if isinstance(target, ast.Subscript) and self._is_state(target.value):
            key = _literal_key(target)
            if key is not None:
                self.reads.setdefault(key, Pattern.STATE_ACCESS)
        elif (
            isinstance(target, ast.Attribute)
            and self._is_state(target.value)
            and not target.attr.startswith("_")
        ):
            self.reads.setdefault(target.attr, Pattern.STATE_ACCESS)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Assigning to the state parameter's own name retargets every later read."""
        if node.id == self.parameter and isinstance(node.ctx, (ast.Store, ast.Del)):
            self.rebound = True

    def visit_Call(self, node: ast.Call) -> None:
        """``Command(update={...})`` (pattern (c)), and mutating calls on the state.

        The callee of a method call is visited as an *object* and not as an attribute read:
        ``state.get("k")`` reads no state key called ``get``, and treating it as one would
        put a method name in the IR's ``input``.
        """
        if _is_command(node):
            self._command(node)
        function = node.func
        if isinstance(function, ast.Attribute):
            if function.attr in MUTATING_METHODS and self._rooted_at_state(function.value):
                self.write_evidence = True
            self.visit(function.value)
        else:
            self.visit(function)
        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def _command(self, node: ast.Call) -> None:
        """§4 output pattern (c): a literal ``Command(update={"k": ...})`` construction."""
        self._update(
            _command_update(node), Pattern.COMMAND_UPDATE, Blocker.COMMAND_UPDATE_NOT_LITERAL
        )

    # ── The state parameter ──────────────────────────────────────────────────────────────

    def _is_state(self, node: ast.expr) -> bool:
        """Whether ``node`` is the state parameter itself — §4's "direct … access"."""
        return (
            self.parameter is not None and isinstance(node, ast.Name) and node.id == self.parameter
        )

    def _rooted_at_state(self, node: ast.expr) -> bool:
        """Whether ``node`` reaches the state parameter through subscripts and attributes.

        Wider than :meth:`_is_state` on purpose, and only for write evidence:
        ``state["messages"].append(m)`` mutates the graph's state at one remove, while the key
        it *reads* is still only the direct one.
        """
        current = node
        while isinstance(current, (ast.Subscript, ast.Attribute)):
            current = current.value
        return self._is_state(current)


# ── Literal readers ──────────────────────────────────────────────────────────────────────


def _is_none(value: ast.expr) -> bool:
    """Whether ``value`` is the literal ``None``."""
    return isinstance(value, ast.Constant) and value.value is None


def _literal_key(node: ast.Subscript) -> str | None:
    """The literal string key of ``state["k"]``, or ``None`` for a computed one."""
    index = node.slice
    if isinstance(index, ast.Constant) and isinstance(index.value, str):
        return index.value
    return None


@dataclass(frozen=True)
class _Update:
    """One written state update as the source shows it — §4's two questions, separately.

    Attributes:
        keys: The literal string keys it spells.
        complete: Whether those are *all* its keys. ``False`` for ``{**other}`` and for a
            computed key — the two non-literal constructions §4 rules out by name.
        evident: Whether a state write is statically evident at all, which is the D-011
            defaults' question and not the multi-return rule's.
    """

    keys: tuple[str, ...] = ()
    complete: bool = True
    evident: bool = False


def _literal_dict(node: ast.Dict) -> _Update:
    """A dict display read as an update: its literal keys, and whether they are all of them."""
    keys: list[str] = []
    complete = True
    for key in node.keys:
        if key is None or not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            complete = False
            continue
        keys.append(key.value)
    return _Update(keys=tuple(keys), complete=complete, evident=bool(keys))


def _is_command(node: ast.Call) -> bool:
    """Whether ``node`` is written as a ``Command(...)`` construction.

    By the name as written — ``Command(...)`` or ``types.Command(...)`` — because shallow
    analysis reads source, not bindings. §4 licenses the construction "in the node body"; what
    the name is bound to at run time is exactly the kind of question DEC-08 rules out.
    """
    function = node.func
    if isinstance(function, ast.Name):
        return function.id == _COMMAND
    return isinstance(function, ast.Attribute) and function.attr == _COMMAND


def _command_update(node: ast.Call) -> _Update:
    """A ``Command`` construction's ``update=``, read the same way as a returned display.

    Three outcomes, and the middle one is why :class:`_Update` has two flags. A ``Command``
    with **no** ``update=`` is a route that writes no state and says so, so it is complete,
    keyless and no evidence. A ``Command(update=<name>)`` **is** evidence of a write — the
    update is right there — whose keys are not readable, so the key set is abandoned. A
    ``Command(**built)`` shows neither: it may carry an update and may not, so the key set is
    abandoned and nothing is claimed about writing.
    """
    for keyword in node.keywords:
        if keyword.arg is None:
            return _Update(complete=False)
        if keyword.arg == "update":
            value = keyword.value
            if not isinstance(value, ast.Dict):
                return _Update(complete=False, evident=True)
            return _literal_dict(value)
    return _Update()


# ── Findings ─────────────────────────────────────────────────────────────────────────────


def _findings(
    keys: Mapping[AnnotationSlot, tuple[InferredKey, ...]],
    default: DefaultRule | None,
    source: NodeSource,
    blockers: tuple[Blocker, ...],
) -> tuple[InferenceFinding, ...]:
    """One record per grade that occurred — §4: "every inferred slot carries a warning".

    Both rows are read through §5's (node id, slot) lookup, so the slots are the record's
    load-bearing field; the rest is the "what it carries" column of the §4 registry.
    """
    findings: list[InferenceFinding] = []
    if keys:
        slots = tuple(slot for slot in ANNOTATION_SLOTS if slot in keys)
        findings.append(
            InferenceFinding(
                grade=SlotGrade.INFERRED,
                slots=slots,
                message=(
                    f"{' and '.join(slots)} inferred from the closed ANNOTATION-API-SPEC §4 "
                    "patterns rather than declared; the claim is heuristic-grade and no other "
                    "slot was upgraded"
                ),
                detail={
                    "surface": "inference",
                    "patterns": {
                        slot: {inferred.key: inferred.pattern.value for inferred in inferred_keys}
                        for slot, inferred_keys in keys.items()
                    },
                    "claims_not_upgraded": list(NEVER_INFERRED),
                    "depth": "shallow-only (DEC-08)",
                },
            )
        )
    if default is not None:
        applied: dict[str, Any] = (
            {"pure": True}
            if default is DefaultRule.NO_WRITE_EVIDENCE
            else {"effect": list(DEFAULT_EFFECT)}
        )
        slot: AnnotationSlot = "pure" if default is DefaultRule.NO_WRITE_EVIDENCE else "effect"
        findings.append(
            InferenceFinding(
                grade=SlotGrade.DEFAULTED,
                slots=(slot,),
                message=(
                    f"no ANNOTATION-API-SPEC §4 pattern set {slot!r}, so the decision D-011 "
                    f"conservative default applied ({default.value}); declare the contract with "
                    "@gebra.contract or a gebra.toml entry to replace it"
                ),
                detail={
                    "surface": "inference",
                    "rule": default.value,
                    "applied": applied,
                    "why": [blocker.value for blocker in blockers],
                    "source": source.rule.value,
                    "declaration_surfaces": ["decorator", "sidecar"],
                },
            )
        )
    return tuple(findings)
