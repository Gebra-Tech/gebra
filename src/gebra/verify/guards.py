"""The P-02 form-(a) guard recognizer — TERMINATION-WITNESS-SPEC §3.

A **syntactic** matcher over the declared ``condition`` string of a conditional edge, and
nothing more. §3's own words: "The recognizer of §3 matches declared *syntax*, nothing more"
(§1.1). It reads declared IR content — never extracted opaque Python, never anything
evaluated — and it answers exactly one question: does this string derive the §3 ``guard``
host shape with a recognized bounded comparison whose counter key is an integer-compatible
member of Σ?

What that does **not** answer is deliberate and permanent (§1.1): whether the declared exit
condition ever evaluates true is the halting problem; whether the counter is actually
advanced is not checked. A recognized guard means the definition names a bound, no more.

**The layering.** Three gates, in order, each with its own rejection so a caller can say
which one fired:

* **L0** — the lexical gate, one left-to-right scan of whitespace-delimited tokens. Its
  four clauses are the decidability discipline: they make every later decision one regular
  expression per conjunct, with no host-Python parsing, ever. L0 rejects **wholesale** —
  "no partial credit, per R5" — which is why :func:`classify_guard` returns a
  :class:`GuardClassification` carrying ``guard=None`` and not a half-filled one.
* **R0** — the derivation. The start symbol is ``guard``, the label-selector ternary
  ``label-literal "if" test "else" label-literal``. A bare comparison with no label
  literals is deliberately not a v1 host shape: the gated label would be undefined.
* **R1** — at least one conjunct of ``test`` must derive ``bounded-comparison``; the
  **leftmost** wins when several do.

R2 (bound direction), R3 (conjunction admitted), R4 (``or``/``not`` rejected — enforced
inside L0), R5 (everything else opaque) and R6 (the gated label is the then-label; the
else-branch is never discharged) are properties of what those three gates produce, and are
recorded on the result rather than re-decided by callers.

**Σ is a separate question from syntax**, so it is a separate call. :func:`classify_guard`
is pure syntax. :func:`qualify_counter_guard` adds R1's second half — counter key in
keys(Σ), with a declared **integer-compatible** type per the §2.1 normative enumeration —
and distinguishes the *R1 near-miss* (§4 qualification-failure path 1: recognized host
shape, unmatched or wrongly-typed identifier, "the likely-misspelled-counter case") from a
plainly opaque string, because §4 requires that near-miss be surfaced and never silently
dropped. :func:`recognize_bounded_comparison` is the catalog §2.4 pseudocode's own entry
point, returning the guard or ``None``.

**Nothing here emits.** No condition ID, no ``WitnessNote``, no ``Failure``, no severity, no
claim class: the outcome labels on :class:`CounterQualification` are this module's own
vocabulary for *why*, and are deliberately not §0.4 registry members. §4's delegation of the
near-miss advisory to the catalog was resolved at DEC-23 (PD-037 Q2): §2.3's note vocabulary
gained ``counter-key-not-qualified`` for exactly this case, and the P-02 validator
(:mod:`gebra.verify.properties.termination_witness`, VAL-07) maps both near-miss outcomes
onto it through an explicit table — this module still emits nothing and hands it a decision
and the evidence for it.

**Fail-closed everywhere.** Every §3 exclusion resolves to "opaque", never to a guess:
non-ASCII identifiers, negative integer literals, ``==``/``!=``, bare comparisons, nested
ternaries, parenthesized/quoted/bracketed constructs, worklist-emptiness guards, and any
type expression that is not exactly ``int``. An unrecognized shape contributes no witness,
which is the safe direction — a missing witness fails a cycle; a wrongly-granted one would
discharge it.

WA-07: the input is a string and the output is frozen dataclasses. Nothing is compiled,
evaluated, imported or executed — :mod:`re` over declared text is the entire engine.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from gebra.ir import StateField

__all__ = [
    "BOUND_DIRECTIONS",
    "CMP_OPS",
    "RESERVED_WORDS",
    "BoundDirection",
    "BoundedComparison",
    "CounterQualification",
    "GuardClassification",
    "GuardGate",
    "QualificationOutcome",
    "RecognizedGuard",
    "classify_guard",
    "is_integer_compatible",
    "qualify_counter_guard",
    "recognize_bounded_comparison",
]


#: The §3 L0 reserved words — reserved **only** when they occur as whole tokens, which is
#: what lets ``transient-failure`` or ``notify`` through untouched.
RESERVED_WORDS: Final = frozenset({"if", "else", "and", "or", "not"})

#: ``cmp-op`` (§3), longest spelling first so the alternation below never commits to ``<``
#: while ``<=`` was meant. ``==`` and ``!=`` are excluded by the grammar, not omitted by
#: accident: "equality is not a bound — one skipped counter value defeats it".
CMP_OPS: Final = ("<=", ">=", "<", ">")

#: R2: which way a recognized comparison bounds its counter, after mirror normalization.
BoundDirection: TypeAlias = Literal["upper", "lower"]

#: Which of the three §3 gates rejected a condition. Not a condition ID; a diagnostic.
GuardGate: TypeAlias = Literal["L0", "R0", "R1"]

#: The result of asking R1's Σ-side question of a syntactically recognized guard. The two
#: near-miss members are §4 qualification-failure path 1; ``"opaque"`` is R5. **None of
#: these is a §0.4 condition ID** — see the module docstring.
QualificationOutcome: TypeAlias = Literal[
    "qualified",
    "counter-key-not-in-state",
    "counter-type-not-integer-compatible",
    "opaque",
]

#: The §2.1 normative enumeration, in full: "the bare type-name string ``"int"``, or an
#: object whose ``type`` member is ``"int"``. **Nothing else qualifies**".
_INTEGER_TYPE: Final = "int"

#: The longest ``int-literal`` this module will recognize — see
#: :func:`_is_representable_literal` for why there has to be one and why it is this one.
_MAX_INT_LITERAL_DIGITS: Final = sys.int_info.str_digits_check_threshold

#: Both directions of ``ws`` are exactly ``{" " | TAB}`` (§3) — never ``\s``, which would
#: admit the newlines and unicode spaces the §3 exclusion list rules out ("``ws`` admits
#: spaces and tabs; no other whitespace").
_WS_CHARS: Final = " \t"

#: ``identifier`` and ``int-literal``, spelled ASCII-explicitly. ``\w``/``\d`` would admit
#: the non-ASCII identifiers §3 excludes by name, and unicode digits with them.
_IDENTIFIER: Final = "[A-Za-z_][A-Za-z0-9_]*"
_INT_LITERAL: Final = "[0-9]+"
_CMP_OP: Final = "|".join(re.escape(operator) for operator in CMP_OPS)
_WS: Final = "[ \t]*"

#: ``bounded-comparison ::= counter-ref ws cmp-op ws int-literal``, and its mirror. Matched
#: against a conjunct's **source slice**, so the ``ws`` positions are the grammar's two and
#: an identifier can never be split across whitespace (``retry _count < 3`` is not one).
#: Anchored by :meth:`re.Pattern.fullmatch` rather than by ``^…$``: Python's ``$`` also
#: matches *before* a trailing newline, which would let one through the §3 exclusion list.
_COMPARISON: Final = re.compile(f"({_IDENTIFIER}){_WS}({_CMP_OP}){_WS}({_INT_LITERAL})")
_MIRRORED_COMPARISON: Final = re.compile(f"({_INT_LITERAL}){_WS}({_CMP_OP}){_WS}({_IDENTIFIER})")

#: R1's "Mirrored forms normalize to counter-on-left (``3 > retry_count`` ≡
#: ``retry_count < 3``)" — the operator reflected about its operands.
_MIRROR: Final[dict[str, str]] = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}

#: R2's two readings. ``<``/``<=`` is the increment-style upper bound (``retry_count < 3``);
#: ``>``/``>=`` the decrement-style lower bound (``remaining_steps > 2``, `positive-02`).
BOUND_DIRECTIONS: Final[dict[str, BoundDirection]] = {
    "<": "upper",
    "<=": "upper",
    ">": "lower",
    ">=": "lower",
}

#: L0's fourth clause: "no parenthesis or bracket characters anywhere (rejects call
#: expressions such as ``len(...)``, grouping, and subscripts)".
_BRACKETS: Final = frozenset("()[]")

#: L0's third clause. Both spellings, because a double quote could otherwise carry a
#: reserved word past the whole-token scan.
_QUOTES: Final = frozenset("'\"")

#: ``plain-char ::= any character except whitespace, "'", '"', "(", ")", "[", "]"``. Only
#: the quote and bracket members are listable; whitespace is asked of the character itself
#: so that a newline or a non-breaking space — neither of which the space/tab tokenizer
#: splits on — cannot sit inside a token and derive ``plain-token``.
_NON_PLAIN: Final = _QUOTES | _BRACKETS


@dataclass(frozen=True, slots=True)
class BoundedComparison:
    """One conjunct that derives ``bounded-comparison`` (§3), normalized per R1/R2.

    ``counter_key`` is the ``counter-ref`` identifier — the counter *position*, which is a
    syntactic fact. Whether it names a member of Σ with an integer-compatible type is R1's
    other half and lives in :func:`qualify_counter_guard`, because §3 recognizes the shape
    and §2.1 qualifies the key, and conflating them would lose the near-miss §4 requires
    be reported.
    """

    counter_key: str
    """The ``counter-ref`` identifier, as written."""
    operator: str
    """The ``cmp-op``, **normalized to counter-on-left** (R1): ``3 > x`` yields ``"<"``."""
    bound: int
    """The ``int-literal``. Never negative — §3 excludes signed literals outright."""
    direction: BoundDirection
    """R2, read off :data:`BOUND_DIRECTIONS` with the normalized operator."""
    mirrored: bool
    """Whether the source spelled the literal first (``3 > retry_count``)."""
    text: str
    """The conjunct's source slice, verbatim — the evidence for everything above."""


@dataclass(frozen=True, slots=True)
class RecognizedGuard:
    """A condition string that passed L0, derived ``guard`` (R0) and carries a comparison.

    R6 is the reason both labels are here and only one of them is called gated: the
    recognized comparison gates the **then-label only**, and "the else-branch is an implicit
    negation context ... so the else-label-edge is NEVER discharged". This value records
    both and discharges neither — assembling S is VAL-07's job, under §4.
    """

    condition: str
    """The declared condition string this was recognized from, verbatim."""
    then_label: str
    """R6's gated label $\\hat{l}$ — the first ``label-literal``, selected when ``test`` holds."""
    else_label: str
    """The second ``label-literal``. Recorded for completeness; never a discharge target."""
    comparison: BoundedComparison
    """R1's recognized comparison — the **leftmost** conjunct that derives one."""
    conjuncts: tuple[str, ...]
    """Every conjunct of ``test``, in source order, as source slices (R3 admits opaque ones)."""
    comparison_index: int
    """Which member of :attr:`conjuncts` :attr:`comparison` came from."""

    @property
    def counter_key(self) -> str:
        """The catalog §2.4 pseudocode's ``m.key``."""
        return self.comparison.counter_key

    @property
    def bound(self) -> int:
        """The catalog §2.4 pseudocode's ``m.bound`` — the §2.3 inventory's ``bound``."""
        return self.comparison.bound


@dataclass(frozen=True, slots=True)
class GuardClassification:
    """What §3 makes of one declared condition string, syntax only.

    Exactly one of :attr:`guard` and :attr:`rejected_by` is set. A rejection carries no
    fragment of the guard it rejected — that is R5's "no partial credit" as a shape rather
    than as a promise, so a caller cannot reach a counter key out of a string L0 threw away.
    """

    condition: str
    """The condition as given (an absent ``condition`` normalizes to the empty string)."""
    guard: RecognizedGuard | None
    """The recognized guard, or ``None`` — never a partially filled one."""
    rejected_by: GuardGate | None
    """Which gate rejected, or ``None`` when recognized."""
    reason: str
    """Why, in one clause — a diagnostic string, never a condition ID."""

    @property
    def recognized(self) -> bool:
        """Whether the string derives ``guard`` with a ``bounded-comparison`` conjunct."""
        return self.guard is not None


@dataclass(frozen=True, slots=True)
class CounterQualification:
    """R1 answered in full: the §3 syntax plus the §2.1 Σ-side test.

    The distinction :attr:`outcome` draws is the one §4 requires. A near-miss is a
    *declared* witness ingredient that failed to qualify, and "a misspelled key never
    silently shrinks coverage" — so it is reported with the identifier that went unmatched.
    An opaque string declared nothing, and needs no advisory. Both contribute no witness.
    """

    classification: GuardClassification
    """The pure-syntax verdict this was built on."""
    guard: RecognizedGuard | None
    """The qualifying guard — ``None`` for both near-misses and for opaque strings."""
    outcome: QualificationOutcome
    """Which of the four §4-relevant cases holds. Not a condition ID."""
    unmatched_identifier: str | None
    """The counter-ref §4 path 1 says the advisory must identify; ``None`` otherwise."""
    declared_type: str | None
    """The rejected type expression, for the wrongly-typed near-miss; ``None`` otherwise."""

    @property
    def qualified(self) -> bool:
        """Whether this guard is a form-(a) witness *source* as far as §3/§2.1 can say.

        §2.1's third qualification item — the DEC-05 D4 exit side condition — is graph-shaped
        and is evaluated by the validator (VAL-07), never here.
        """
        return self.guard is not None


@dataclass(frozen=True, slots=True)
class _Token:
    """One whitespace-delimited token with its source span, so slices stay verbatim."""

    text: str
    start: int
    end: int


def _tokenize(condition: str) -> list[_Token]:
    """Scan into whitespace-delimited tokens, where whitespace is space and tab only.

    Deliberately not ``str.split()``: that splits on every unicode whitespace character,
    which would silently admit the newlines §3's exclusion list rules out. A token here may
    therefore *contain* a newline — and then derives neither ``plain-token`` nor
    ``label-literal``, so R0 rejects it. Fail-closed, and by the grammar rather than by the
    tokenizer guessing.
    """
    tokens: list[_Token] = []
    index = 0
    length = len(condition)
    while index < length:
        if condition[index] in _WS_CHARS:
            index += 1
            continue
        start = index
        while index < length and condition[index] not in _WS_CHARS:
            index += 1
        tokens.append(_Token(condition[start:index], start, index))
    return tokens


def _is_label_literal(text: str) -> bool:
    """``label-literal ::= "'" label-char { label-char } "'"``; ``label-char`` bars ``'``.

    So the token is a single-quoted run of at least one non-quote, non-whitespace character.
    A double quote inside is admitted by the grammar (``label-char`` excludes only ``'`` and
    whitespace) and by L0, which permits quote characters inside the two label-literal
    tokens.
    """
    if len(text) < 3 or text[0] != "'" or text[-1] != "'":
        return False
    inner = text[1:-1]
    return "'" not in inner and not any(character.isspace() for character in inner)


def _is_plain_token(text: str) -> bool:
    """``plain-token ::= plain-char { plain-char }`` with the "not a reserved word" side
    condition.

    That side condition cannot fire once L0 has passed and the host shape has been anchored:
    L0 leaves exactly one ``if`` and one ``else``, both consumed by the ``guard`` production,
    bans ``or``/``not`` outright, and ``and`` is the conjunct separator — so no conjunct
    token is ever reserved. It is written anyway because it is part of the production, and
    is exercised directly by unit test rather than through a condition string.
    """
    if not text or text in RESERVED_WORDS:
        return False
    return not any(character in _NON_PLAIN or character.isspace() for character in text)


def _rejected(condition: str, gate: GuardGate, reason: str) -> GuardClassification:
    """Every rejection in one place, so none of them can accidentally leak a fragment."""
    return GuardClassification(condition=condition, guard=None, rejected_by=gate, reason=reason)


def _l0_failure(condition: str, tokens: list[_Token]) -> str | None:
    """The §3 L0 gate: the four clauses, in the order §3 writes them.

    Returns the first clause violated, or ``None`` when the string passes. Every clause is
    a property of the token scan alone — that is what makes L0 lexical, and what makes the
    conjunct analysis below one regular expression with no scoping to do: "opaque regions
    cannot contain hidden operators, because any construct that could hide one (quotes,
    parens, nesting, ``or``, ``not``) already made the whole string opaque".

    The third clause is read as *the first and last tokens*, which is where the ``guard``
    production puts its two label literals; a quote anywhere else is rejected here. The
    reading is never verdict-bearing — ``plain-char`` and ``counter-ref`` both exclude quote
    characters, so a quote in any other token fails R0 too — it only fixes which gate is
    named in the diagnostic.
    """
    spellings = [token.text for token in tokens]
    if spellings.count("if") != 1:
        return f"L0 requires exactly one `if` token; found {spellings.count('if')}"
    if spellings.count("else") != 1:
        return f"L0 requires exactly one `else` token; found {spellings.count('else')}"
    for word in ("or", "not"):
        if word in spellings:
            return f"L0 rejects any `{word}` token (R4: disjunction and negation)"
    for position, token in enumerate(tokens):
        if position in (0, len(tokens) - 1):
            continue
        if any(character in _QUOTES for character in token.text):
            return (
                "L0 admits quote characters only inside the two label-literal tokens; "
                f"token {position} is {token.text!r}"
            )
    for character in condition:
        if character in _BRACKETS:
            return f"L0 rejects parenthesis and bracket characters; found {character!r}"
    return None


def _split_conjuncts(tokens: list[_Token]) -> list[list[_Token]] | None:
    """Cut ``test`` at its reserved ``and`` tokens (§3: "Conjunct boundaries are the
    reserved ``and`` tokens").

    Returns ``None`` when any conjunct comes out empty — a leading, trailing or doubled
    ``and`` — because ``conjunct`` derives at least one token in either alternative.
    """
    conjuncts: list[list[_Token]] = [[]]
    for token in tokens:
        if token.text == "and":
            conjuncts.append([])
        else:
            conjuncts[-1].append(token)
    if any(not conjunct for conjunct in conjuncts):
        return None
    return conjuncts


def _slice(condition: str, conjunct: list[_Token]) -> str:
    """A conjunct's verbatim source text, internal whitespace intact."""
    return condition[conjunct[0].start : conjunct[-1].end]


def _is_representable_literal(digits: str) -> bool:
    """Whether an ``int-literal``'s value can be rendered — the one narrowing this module
    makes to §3, and it makes it **fail-closed**.

    §3 writes ``int-literal ::= digit { digit }`` with no length bound, and no conforming
    implementation of that exists. CPython caps string↔int conversion at
    ``sys.get_int_max_str_digits()`` — **because the conversion is quadratic** (the cap is the
    CVE-2020-10735 mitigation) — so a long literal has three possible fates and all three are
    defects: ``int()`` raises ``ValueError`` inside a validator; hand-accumulating the digits
    reproduces the quadratic cost without the guardrail, so a ~1 MB declared condition costs
    minutes; and a value that *is* accumulated cannot be rendered, so ``repr()``, ``str()``
    and JSON serialization of any report carrying it raise later, further from the cause.

    So an over-long literal is not recognized, and the conjunct falls through to
    ``opaque-conjunct`` — no witness, which is the safe direction: narrowing the grammar can
    only *remove* discharges, never grant one §3 would deny, and §1.1 makes a missing witness
    the failing side. The budget is read off the interpreter rather than picked:
    ``sys.int_info.str_digits_check_threshold`` is the smallest value
    ``sys.set_int_max_str_digits()`` accepts, so a literal within it is renderable under every
    legal configuration and its conversion is trivially cheap. **That this narrowing exists at
    all is the implementation's call, not §3's** — recorded as such, and routed for ruling as
    VAL-D5 Q5.
    """
    return len(digits) <= _MAX_INT_LITERAL_DIGITS


def _match_comparison(text: str) -> BoundedComparison | None:
    """``bounded-comparison`` against one conjunct's source slice, both operand orders.

    Anchored with :meth:`re.Pattern.fullmatch`: the *whole* conjunct must derive the
    production, since ``conjunct ::= bounded-comparison | opaque-conjunct`` offers no way
    to embed one in the other. That is what keeps ``retry_count < 3 x`` out.

    A conjunct whose literal is longer than :func:`_is_representable_literal` admits returns
    ``None`` here and is then offered to ``opaque-conjunct`` like any other unmatched text —
    so the narrowing costs one derivation, never a raise and never a special case downstream.
    """
    direct = _COMPARISON.fullmatch(text)
    if direct is not None and _is_representable_literal(direct.group(3)):
        operator = direct.group(2)
        return BoundedComparison(
            counter_key=direct.group(1),
            operator=operator,
            bound=int(direct.group(3)),
            direction=BOUND_DIRECTIONS[operator],
            mirrored=False,
            text=text,
        )
    mirrored = _MIRRORED_COMPARISON.fullmatch(text)
    if mirrored is None or not _is_representable_literal(mirrored.group(1)):
        return None
    operator = _MIRROR[mirrored.group(2)]
    return BoundedComparison(
        counter_key=mirrored.group(3),
        operator=operator,
        bound=int(mirrored.group(1)),
        direction=BOUND_DIRECTIONS[operator],
        mirrored=True,
        text=text,
    )


def classify_guard(condition: str | None) -> GuardClassification:
    """Classify one declared ``condition`` string against §3 — L0, then R0, then R1.

    Pure syntax: Σ is not consulted, so a recognized result says the string *derives* the
    host shape with a bounded comparison, never that the counter it names exists. Use
    :func:`qualify_counter_guard` for the Σ-side half of R1.

    An absent condition (``None``) is not an error and not a special case — it has no
    tokens, so L0's first clause rejects it like any other string that is not a ternary.

    >>> found = classify_guard("'retry' if response is stale and retry_count < 3 else 'done'")
    >>> found.recognized
    True
    >>> found.guard.counter_key, found.guard.bound, found.guard.comparison.direction
    ('retry_count', 3, 'upper')
    >>> found.guard.then_label, found.guard.else_label
    ('retry', 'done')
    >>> found.guard.conjuncts
    ('response is stale', 'retry_count < 3')

    R5 has no partial credit, and neither does this: a rejection's ``guard`` is ``None``
    even when a perfectly good comparison is sitting inside the string.

    >>> spoiled = classify_guard("'retry' if retry_count < 3 or force else 'done'")
    >>> spoiled.recognized, spoiled.rejected_by, spoiled.guard
    (False, 'L0', None)
    """
    text = condition if condition is not None else ""
    tokens = _tokenize(text)

    failure = _l0_failure(text, tokens)
    if failure is not None:
        return _rejected(text, "L0", failure)

    # R0 — derive `guard`, the label-selector ternary. L0 has already fixed the multiplicity
    # of `if` and `else`, so their positions are the whole of the host-shape question.
    if len(tokens) < 5:
        return _rejected(text, "R0", "R0 needs the full ternary host shape; too few tokens")
    if tokens[1].text != "if" or tokens[-2].text != "else":
        return _rejected(
            text, "R0", "R0 host shape is `<label> if <test> else <label>`; `if`/`else` misplaced"
        )
    if not _is_label_literal(tokens[0].text):
        return _rejected(
            text,
            "R0",
            f"R0 needs a quoted then-label; found {tokens[0].text!r} "
            "(a bare comparison leaves the gated label undefined)",
        )
    if not _is_label_literal(tokens[-1].text):
        return _rejected(text, "R0", f"R0 needs a quoted else-label; found {tokens[-1].text!r}")

    conjuncts = _split_conjuncts(tokens[2:-2])
    if conjuncts is None:
        return _rejected(text, "R0", "R0: `and` must join two non-empty conjuncts")

    slices = tuple(_slice(text, conjunct) for conjunct in conjuncts)
    comparisons = [_match_comparison(one) for one in slices]
    for position, conjunct in enumerate(conjuncts):
        if comparisons[position] is not None:
            continue
        # R3 admits opaque conjuncts alongside the recognized one, but only as
        # `opaque-conjunct` — a conjunct deriving neither production sinks the derivation.
        if not all(_is_plain_token(token.text) for token in conjunct):
            return _rejected(
                text,
                "R0",
                f"R0: conjunct {slices[position]!r} derives neither "
                "`bounded-comparison` nor `opaque-conjunct`",
            )

    # R1 — at least one conjunct derives `bounded-comparison`; the leftmost is the one.
    for position, comparison in enumerate(comparisons):
        if comparison is None:
            continue
        guard = RecognizedGuard(
            condition=text,
            then_label=tokens[0].text[1:-1],
            else_label=tokens[-1].text[1:-1],
            comparison=comparison,
            conjuncts=slices,
            comparison_index=position,
        )
        return GuardClassification(
            condition=text,
            guard=guard,
            rejected_by=None,
            reason=f"recognized: {comparison.direction} bound on `{comparison.counter_key}`",
        )
    return _rejected(text, "R1", "R1 needs a `bounded-comparison` conjunct; `test` has none")


def is_integer_compatible(declared: str | StateField | None) -> bool:
    """The §2.1 **normative enumeration** of integer-compatible, and only it.

    "A state key is integer-compatible iff its ledger-§2 type expression is the bare
    type-name string ``"int"``, or an object whose ``type`` member is ``"int"`` (the
    ``reducer`` and ``optional`` members are irrelevant to qualification ...). **Nothing
    else qualifies** — not ``"float"``, ``"number"``, ``"str"``, ``"list"``, or any other
    type expression."

    Fail-closed by construction: an unrecognized type expression — including ``None``, a
    widened spelling like ``"Optional[int]"``, or a differently-cased ``"Int"`` — is not
    integer-compatible, so the guard contributes no witness.
    """
    if isinstance(declared, StateField):
        return declared.type == _INTEGER_TYPE
    return declared == _INTEGER_TYPE


def qualify_counter_guard(
    condition: str | None,
    state: Mapping[str, str | StateField] | None,
) -> CounterQualification:
    """R1 in full: the §3 syntax, then keys(Σ) membership and §2.1 integer compatibility.

    The four outcomes are §4's, not this module's invention. ``"opaque"`` is R5 — the string
    declared nothing, and §4 asks for no diagnostic. The two near-misses are §4
    qualification-failure path 1: the host shape derived and a comparison was recognized,
    but the counter-ref names no member of Σ or names one whose declared type is not
    integer-compatible. §4 requires that case be surfaced with the unmatched identifier —
    "a misspelled key never silently shrinks coverage" — and delegates the advisory's
    condition ID and severity to the catalog, so this returns the evidence and emits
    nothing.

    ``state`` is ``ir.state``: a mapping of key to a bare type-name string or a
    :class:`~gebra.ir.StateField`. An IR with no ``state`` block has an empty Σ, in which
    every recognized guard is a key-not-in-state near-miss.
    """
    classification = classify_guard(condition)
    guard = classification.guard
    if guard is None:
        return CounterQualification(
            classification=classification,
            guard=None,
            outcome="opaque",
            unmatched_identifier=None,
            declared_type=None,
        )

    key = guard.counter_key
    schema: Mapping[str, str | StateField] = state if state is not None else {}
    if key not in schema:
        return CounterQualification(
            classification=classification,
            guard=None,
            outcome="counter-key-not-in-state",
            unmatched_identifier=key,
            declared_type=None,
        )

    declared = schema[key]
    if not is_integer_compatible(declared):
        return CounterQualification(
            classification=classification,
            guard=None,
            outcome="counter-type-not-integer-compatible",
            unmatched_identifier=key,
            declared_type=declared.type if isinstance(declared, StateField) else declared,
        )

    return CounterQualification(
        classification=classification,
        guard=guard,
        outcome="qualified",
        unmatched_identifier=None,
        declared_type=_INTEGER_TYPE,
    )


def recognize_bounded_comparison(
    condition: str | None,
    state: Mapping[str, str | StateField] | None,
) -> RecognizedGuard | None:
    """The catalog §2.4 pseudocode's ``recognize_bounded_comparison(g.condition, Sigma)``.

    Returns the qualifying guard — whose ``counter_key`` and ``bound`` are the pseudocode's
    ``m.key`` and ``m.bound`` — or ``None`` for every non-qualifying string, which is the
    pseudocode's ``NONE`` and its ``continue  # R5 — no partial credit``.

    A caller that needs to tell a near-miss from an opaque string (§4 path 1 requires the
    advisory) calls :func:`qualify_counter_guard` instead; this collapses both to ``None``
    exactly as the pseudocode does.
    """
    return qualify_counter_guard(condition, state).guard
