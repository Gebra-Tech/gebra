"""The round-trip drift suite — designated corpus fixtures against live extractor output.

Normative authority: D-10 In-Scope 5 and Deliverable 6 ("for a designated subset of fixtures,
a matching mini LangGraph builder script exists in the package repo; under the pinned
``langgraph``/``langchain-core`` versions, ``gebra.extract()`` output must equal the
hand-written ``ir:`` block"), under D-10's own risk row: *hand-written fixtures drift from what
``gebra.extract()`` actually emits — golden tests pass against an IR no one produces.*

**What a pair is.** One vendored fixture, one **mini builder script** under
:mod:`tests.drift.builders`, and the claim that extracting the second reproduces the first.
The builder is a live ``StateGraph``: real nodes, real edges, a real state schema, and the
ANNOTATION-API-SPEC §1 decorators that put the fixture's ``annotations`` block on it. Nothing
is stubbed and nothing is loaded from the fixture — if the script and the fixture agree it is
because the extractor and the corpus author agree.

**The comparison is canonical, not model equality, and canonicalization is what makes the two
documents comparable at all.** Two IR-SPEC §6 rules stand between an authored fixture and an
extracted document even when they say the same thing: §6.2 sorts ``nodes[]`` and ``edges[]``,
while a fixture is authored in reading order and the extractor emits its own deterministic
order (neither of which is §6.2's); and §6.3's representation-normalization collapses the
bare-vs-object ``state`` value forms and the scalar-vs-list ``entry``/``finish`` forms, either
of which a fixture may legally author. Comparing the models directly would therefore fail every
pair on form alone and say nothing about content. So the pair is held to the operation IR-SPEC
§1.2 calls *extractor conformance*, with a fixture in the golden's place — the substitution is
D-10 Deliverable 6's, not the spec's, since §1.3 assigns the property corpus to *document*
conformance: canonical bytes **byte-identical**, ``graph_version`` **string-equal**. §1.2's
sentence carries over unchanged — "there is no partial conformance in either class: a single
differing byte in canonical form is non-conformance" — and :mod:`tests.drift.roundtrip` computes
a structural diff only in order to *render* a failure, never to decide one.

**Warning-free is part of the claim.** INTROSPECTION-SPEC §8 makes a warning-free extraction
"part of the strict-mode bar", and a pair that matched only because §4 shallow inference
guessed the slot the fixture declares would be a weaker pair wearing a green tick. So every
pair declares the warnings it expects, and sixteen of the seventeen declare none: every
annotation slot the fixture carries is *declared* on the builder, at the ANNOTATION-API-SPEC §3
decorator tier, and nothing is inferred or defaulted. (The sixteenth is a negative fixture whose
own P-06 defect is an annotation-level one, so the resolution chain says so — see
:mod:`tests.drift.pairs`.)

That discipline has one visible consequence, asserted rather than left to be found. A fixture
node that carries neither ``effect`` nor ``pure`` leaves that slot **open**, and an open slot is
exactly what §4 fills — so the script closes it with ``@gebra.contract(effects=[])``. IR-SPEC
§6.3 omit-normalizes an empty ``effect`` away, so the two canonicalize identically and the
digests agree; at *model* level the fixture reads ``effect: None`` and the extraction
``effect: ()``. ``test_round_trip.py`` compares the models too and requires every difference
across the coherent set to be exactly that one, on exactly such a node.

**Which fixtures are designated, and why not all seventy-one** — see :mod:`tests.drift.pairs`, which
carries the reachability rule and the two constructs that put the rest of the corpus out of
reach.

**WA-07.** Every node body in every builder here is armed: it records itself in
:data:`tests.drift.sentinels.TRIPPED` and raises a :class:`BaseException` subclass, so a body
that runs cannot be swallowed by an ``except Exception`` and fails the test that ran it. The
ledger is read on entry to *and* exit from every test. This suite adds **no extraction path** —
it calls ``gebra.extract()`` and nothing else — so no new tripwire is owed under WA-07's
"every new extraction path lands with tripwire coverage"; the arming here is a redundant guard
on top of the per-path tripwires (``tests/test_never_invokes.py`` is the index), not their
replacement. Nothing is ever compiled: the subject is the builder level throughout, per
PD-023 D4.
"""
