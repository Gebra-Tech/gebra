# P-08 `determinism-replay`

P-08 asks one question about a workflow definition: **does a node that declares determinism pin
the things that declaration would have to pin to be coherent?**

Not "is this node deterministic". That is a fact about a provider at run time, and no document
settles it. `@gebra.deterministic` is a claim the author makes so that other things — memoisation,
replay, a cached transcript — may be reasoned about; P-08 checks that the claim is internally
coherent with the rest of what the node declares, and stops there. A node whose declared effects say
it calls a remote model, and whose determinism claim pins no seed, has said two things that do not
fit together, and that is a defect a document can settle.

Every P-08 finding is **HEURISTIC** and **WARNING**, always — and P-08 is the only property in this
release whose findings never fail a gate on their own. A run with nothing else wrong exits `0` with a
P-08 finding in it, and the finding becomes a gate only under a strict policy — bare, or naming this
property (§0.2).
P-08 is the catalog's own example of what strict mode is for. This page is about reading those
findings: what the validator checks, what each field of its witness and its failure record means,
and where the claim stops.

!!! note "Section numbers, and where they point"

    `§` references are to **PROPERTY-CATALOG-SPEC** — §8 is its P-08 section, Appendix B its
    LLM-determinism support, and §0 the shared report envelope. That is an internal contract
    document and is not published with this site; the numbers are here so a statement can be
    *checked* against it rather than taken on trust. The transcripts are not spec-derived: they
    are what this release printed.

!!! note "Following along"

    Every example here starts from the vendored property-fixture corpus in this repository,
    `tests/fixtures/properties/` — one YAML document per fixture, carrying an IR and the verdict
    the specification expects for it. Three of them go on to edit the loaded document and
    re-validate it, which is how the page shows shapes the corpus does not carry. To run them
    yourself, clone the repository and put its root on `PYTHONPATH` — the corpus is located from
    `tests.__file__`, so an example works from any directory. Nothing here builds or compiles a
    LangGraph graph, and no example calls a model: a fixture is data, and the illustrative builder
    code some fixtures carry is an inert string that is never compiled or run.

## What P-08 checks

P-08 walks `nodes[]` once and reads two annotation slots. It never reads `edges[]`, never reads the
state schema, and never builds a graph — the negative is stated in the specification on purpose
(§8.7: "the validator must not couple to topology"), and
[the round trip below](#what-p-08-reads) is that statement executed. Three rules decide what it
reports.

**A claim is what raises the question, and only a claim.** A node with no `deterministic`
annotation is not examined and does not appear in the report, however obviously it calls a model.
A node declaring `deterministic: false` has made the explicit disclaimer, which is a claim about
*not* claiming, and is skipped the same way. What is left — `deterministic: true`, or the object
form `{seed: N}` or `{seed: N, temperature: T}` — is a claim, and every claim is recorded.

**LLM-backed is decided by the declared effect tags, and by nothing else.** A node is LLM-backed
when its declared `annotations.effect` contains `external` or `network` — the effect-vocabulary
proxy for "wraps a remote LLM call" (Appendix B C-1). Those two tags are the whole trigger set.
A claim on a node without either is *trivially coherent*: pure local computation carries no pinning
obligation, so the claim is recorded and no condition applies. This is a declaration being read,
not code being inspected, and
[what that costs you](#a-claim-on-a-node-with-no-llm-evidence) is worth knowing.

**An LLM-backed claim has to pin both halves.** The object form must be used, so that a seed is
named at all (C-2), and that object must carry `temperature: 0`, compared numerically so `0` and
`0.0` are the same value (C-3). Absent and nonzero are the same defect and carry the same condition
ID; they differ only in [what the record can show you](#one-condition-two-shapes-of-evidence).

Two things, then, that P-08 can say:

| Condition | What it requires | Condition ID | Anchor |
|---|---|---|---|
| **a seed is pinned** | an LLM-backed node's determinism claim uses the object form, so a seed is named somewhere | `deterministic-llm-seed-unpinned` | the node, with the annotation form and the node's full declared effect set |
| **the temperature is pinned to zero** | that same object carries `temperature: 0` — the field absent and the field nonzero are both defects | `deterministic-llm-temperature-unpinned` | the node, with the seed it pinned and the temperature it declared, when it declared one |

Those two strings are the whole P-08 vocabulary. They are in the frozen condition-ID registry and
emittable by this release (§0.4) — a validator may not emit a string the registry does not hold, and
[what gebra checks](../concepts/what-gebra-checks.md#the-diagnostic-vocabulary-is-frozen) explains
why that matters downstream.

One shape that is *not* a P-08 finding: an object form with no `seed` at all. That document does not
validate as IR, so it never reaches a validator — a tool error, exit `2`, no verdict (§0.2).

## A pass carries a ledger of claims

A passing property does not return a bit. It returns a **witness**: structured, re-checkable
evidence, never prose (§0.3). P-08's is the list of determinism claims the document makes and what
each one pinned, in the form pinned by decision record DEC-11. The fixture below is the catalog's
own classifier, fully pinned.

<!-- gebra:example id=a-pass-and-its-claim-ledger -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"

fixture = load_fixture(CORPUS / "positive-01-pinned-seed-zero-temp-classifier.yaml")
report = run_property("determinism-replay", fixture.ir)

print(f"fixture   {fixture.fixture_id}")
print(f"graph     {len(fixture.ir.nodes)} nodes, {len(fixture.ir.edges)} authored edges")
for node in fixture.ir.nodes:
    declared = node.annotations
    if declared is None or declared.deterministic is None:
        continue
    spec = declared.deterministic
    print(f"declared  {node.id}: seed {spec.seed}, temperature {spec.temperature}")
    print(f"          effect {list(declared.effect or ())}")
print(f"result    {report.result} — the failure field is {report.failure}")
print("witness   serialized in the report profile:")
print(to_json(report.witness))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-pass-and-its-claim-ledger -->
```text
fixture   determinism-replay/positive-01-pinned-seed-zero-temp-classifier.yaml
graph     3 nodes, 2 authored edges
declared  classify_request: seed 42, temperature 0.0
          effect ['network', 'external']
result    pass — the failure field is None
witness   serialized in the report profile:
{
  "kind": "determinism",
  "claims": [
    {
      "node": "classify_request",
      "llm_backed": true,
      "seed": 42,
      "temperature": 0.0,
      "divergence_handling": "logged"
    }
  ],
  "caveat": "provider-seed-reproducibility-not-guaranteed",
  "claim_class": "heuristic"
}
equals the fixture's own expected block: True
```

`receive_request` collects a traveller's message, `classify_request` sends it to a model, and
`plan_itinerary` builds from what came back. The middle node declares `@gebra.deterministic(seed=42)`
with `temperature: 0`, and declares the effects that make the pinning obligatory in the first place.

**`kind`** is the discriminator. The envelope's witness type is a union with one member per
property, and every consumer reads `kind` before anything else (§0.3).

**`claims` holds one record per claim, in node-identifier order** — not one per node, and not one
per LLM call. A document that declares no determinism anywhere passes with an empty list, which is
[a pass that checked something](#a-claim-is-what-p-08-checks-not-a-node) and found nothing to check.

**`node` and `llm_backed` are the question that was asked.** `llm_backed` is the C-1 answer, and it
decides which of two shapes the rest of the record takes: an LLM-backed claim carries `seed`,
`temperature` and `divergence_handling`, and a non-LLM claim carries `basis` and
`pinning_required` instead. The unused members are absent, not null — the report profile drops what
is unset.

**`seed` and `temperature` are what the annotation pinned**, echoed back so a reader can see the
configuration the coherence verdict was reached about. `temperature` on a coherent LLM-backed claim
is always `0`; there is no other value that gets here.

**`divergence_handling` is a policy echo, and it is worth being clear about what it is not.** The
value is the constant `logged` on every coherent LLM-backed claim. It restates the design rule the
annotation contract carries — replay divergence is logged, never silently accepted — and it has **no
carrier in the IR**: nothing in the document said so, nothing was read to produce it, and it is not
evidence that anything logs anything. Keeping it in the witness rather than dropping it was ruled
explicitly (decision record DEC-14), and it is here as a reminder of the obligation the claim
brings with it.

**`caveat` is mandatory, and its absence is meaningful.** A witness carrying any LLM-backed claim
carries `provider-seed-reproducibility-not-guaranteed`; a witness carrying none carries no caveat
at all. The model enforces the "if and only if" rather than trusting the validator to remember it
(§8.3), which makes the caveat part of the shape of a P-08 pass rather than a courtesy added to it.
[What that caveat is doing there](#what-a-pass-does-not-claim) is the last section of this page.

**`claim_class` is on the witness itself**, `heuristic`, in-band. A P-08 pass is an advisory result:
it says the declarations fit together, and it does not have a stronger reading available to it.

**The last line is the corpus's own claim, re-run.** `models_equivalent` is §0.3's comparison: model
equality, with set comparison on the fields the specification marks order-free. The validator's
output and the fixture's `expected:` block validate into the *same* class, so the frozen example and
the result type cannot drift apart.

!!! note "`run_property` versus `verify()`"

    `run_property` is the single-property dispatch, which is what a page about one validator wants.
    A whole run goes through `verify()`, which additionally derives the gate, answers for all
    thirteen catalog properties, and refuses a document whose `ir_version` this build's validators
    are not defined over — a tool error, exit `2`, no verdict (§0.2).
    [Verify and interpret](../tutorials/verify-and-interpret.md) works through a full run.

## A failure names the node and the form it declared

The other half of the envelope. A failing property fills `failure` with a structured record: the
violated **condition ID**, the **location** it was found at, its **severity** and its **claim class**
(§0.3). The fixture below is the corpus's own counterpart to the one above — the same shape of node,
with the pinning taken away.

<!-- gebra:example id=a-failure-and-its-record -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"

fixture = load_fixture(CORPUS / "negative-01-seedless-deterministic-llm-classifier.yaml")
report = run_property("determinism-replay", fixture.ir)
failure = report.failure

print(f"fixture   {fixture.fixture_id}")
print(f"result    {report.result} — the witness field is {report.witness}")
print(f"findings  1 primary + {len(failure.co_failures or ())} same-property co-finding")
print("record    serialized in the report profile:")
print(to_json(failure))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")

COUNTERPARTS = (
    ("positive-01", "positive-01-pinned-seed-zero-temp-classifier"),
    ("negative-01", "negative-01-seedless-deterministic-llm-classifier"),
)

print("\nthe counterpart pair, claiming node by claiming node:")
for label, name in COUNTERPARTS:
    ir = load_fixture(CORPUS / f"{name}.yaml").ir
    verdict = run_property("determinism-replay", ir).result
    for node in ir.nodes:
        declared = node.annotations
        if declared is None or declared.deterministic is None:
            continue
        spec = declared.deterministic
        form = (
            "bare boolean true"
            if spec is True
            else f"object seed={spec.seed} temperature={spec.temperature}"
        )
        print(f"  {label}  {node.id:18}{form}")
        print(f"{'':15}effect {list(declared.effect or ())} -> {verdict}")
```

<!-- gebra:output id=a-failure-and-its-record -->
```text
fixture   determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml
result    fail — the witness field is None
findings  1 primary + 0 same-property co-finding
record    serialized in the report profile:
{
  "property_condition": "deterministic-llm-seed-unpinned",
  "location": {
    "kind": "node",
    "node": "classify_intent",
    "annotation": "deterministic",
    "form": "bare-boolean",
    "effects": [
      "network",
      "external"
    ]
  },
  "severity": "warning",
  "claim_class": "heuristic",
  "remediation": "The claim is recorded. Pin the configuration — @gebra.deterministic(seed=N) with temperature=0 — or drop the claim; replay divergence must be logged either way."
}
equals the fixture's own expected block: True

the counterpart pair, claiming node by claiming node:
  positive-01  classify_request  object seed=42 temperature=0.0
               effect ['network', 'external'] -> pass
  negative-01  classify_intent   bare boolean true
               effect ['network', 'external'] -> fail
```

Field by field, because every one of them is load-bearing.

**`property_condition`** is the machine-readable half of the finding: the stable string to key on
rather than parsing prose. It is a registry entry, frozen verbatim (§0.4).

**`location` is typed, and P-08 extends the type.** The envelope has six structural anchors — node,
edge, cycle, SCC, state-key and path — and P-08 uses the **node** anchor, so `kind` is `"node"` and
`node` names the node. Five evidence members ride on top of it. `annotation` is the required one and
is always `"deterministic"`, naming the slot the finding is about; the other four are optional, and
which of them appear tells you which condition you are reading without looking at the ID. `form` is
`"bare-boolean"` on a seed-unpinned finding — the whole of what went wrong, since a boolean has
nowhere to put a seed. `effects` carries the node's
*full declared set* as the evidence for LLM-backedness, so a record can name tags that are not the
reason it is there — and unlike P-06's counterpart member, this one is **not** marked order-free by
§8.3, so it is compared as written and echoes the order the node declared. `seed` and `temperature`
are the temperature-unpinned pair, and
[one of them can be absent](#one-condition-two-shapes-of-evidence).

**`severity` and `claim_class` are read off the registry, not restated by the validator.** For P-08
that is `warning` and `heuristic` on every finding this property can produce, and they stay that way
[under a strict policy too](#every-finding-is-a-warning-and-strict-mode-is-the-only-gate).

**`remediation` is set, and P-08 is the only property in this release that sets it.** It is the
closing paragraph of the specification's own warning template (Appendix B §B.3) — display-only
prose, never parsed, and the one place a P-08 record speaks to a person rather than to a consumer.
Everything a tool branches on is structured beside it. There is one such paragraph per condition and
it carries no substituted values, so the same text arrives with every finding of that condition; the
part that varies is the record around it.

**The remaining optional members are absent, not empty.** `co_failures` is unset here because this
document has one claiming node — [a document with two](#two-findings-one-record) fills it.
`advisories` carries **cross-property** WARNING-class side findings, which P-08 itself never sets;
the direction that does happen is the other one, where a P-08 finding rides *another* property's
primary as an advisory, which is the shape `mixed/03`'s frozen block records for a run this release
does not perform. `subsumed_by` states that a finding is owned upstream, and **no validator in this
release sets it**. `notes` carries structured same-property notes, and P-08's vocabulary has no note
kinds, so it never carries one.

**And the counterpart pair is the whole property in four lines.** `classify_request` and
`classify_intent` are the same shape of node doing the same job, declaring the same two effect tags. One
declares an object with both halves pinned; the other declares a bare `true`. That is what the two
verdicts turn on. If you are holding a `deterministic-llm-seed-unpinned` finding, the repair is one
of exactly two things: pin the configuration, or drop the claim — and the remediation says so,
because either one leaves the document coherent.

## Every fixture in the corpus

The corpus's `determinism-replay` directory is where the property is pinned: three positives and
three negatives, covering both condition IDs, both shapes of claim record, and the vacuous case.
(The specification's own §8.6 tables two of each; the third positive and the third negative were
authorized separately by decision record DEC-16 and written under card TE-14, and the count here is
the directory's.) Running the validator over all six at once is the shortest tour of what P-08 can
say.

<!-- gebra:example id=every-fixture-in-the-corpus -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import DeterminismNodeLocation, models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"

EVIDENCE = tuple(
    name for name, field in DeterminismNodeLocation.model_fields.items() if not field.is_required()
)


def render(name, value):
    return f"{name} {list(value)}" if name == "effects" else f"{name} {value}"


agreed = 0
fixtures = [load_fixture(path) for path in sorted(CORPUS.glob("*.yaml"))]
for fixture in fixtures:
    report = run_property("determinism-replay", fixture.ir)
    agreed += models_equivalent(report, fixture.expected_report())
    print(fixture.path.stem)
    if report.result == "pass":
        witness = report.witness
        print(f"    pass  {len(witness.claims)} claim(s), caveat {witness.caveat or 'absent'}")
        for claim in witness.claims:
            pinned = (
                f"seed {claim.seed}, temperature {claim.temperature}, "
                f"divergence_handling {claim.divergence_handling}"
                if claim.llm_backed
                else f"basis {claim.basis}, pinning_required {claim.pinning_required}"
            )
            print(f"          {claim.node} llm_backed {claim.llm_backed}")
            print(f"            {pinned}")
    else:
        location = report.failure.location
        set_here = [name for name in EVIDENCE if getattr(location, name) is not None]
        evidence = "; ".join(render(name, getattr(location, name)) for name in set_here)
        print(f"    fail  {report.failure.property_condition} at {location.node}")
        print(f"          evidence {evidence}")

print(f"\n{agreed} of {len(fixtures)} reports equal the fixture's own expected block")
```

<!-- gebra:output id=every-fixture-in-the-corpus -->
```text
negative-01-seedless-deterministic-llm-classifier
    fail  deterministic-llm-seed-unpinned at classify_intent
          evidence form bare-boolean; effects ['network', 'external']
negative-02-seeded-llm-extractor-hot-temperature
    fail  deterministic-llm-temperature-unpinned at extract_preferences
          evidence seed 7; temperature 0.7
negative-03-seeded-llm-temperature-field-absent
    fail  deterministic-llm-temperature-unpinned at rank_destinations
          evidence seed 11
positive-01-pinned-seed-zero-temp-classifier
    pass  1 claim(s), caveat provider-seed-reproducibility-not-guaranteed
          classify_request llm_backed True
            seed 42, temperature 0.0, divergence_handling logged
positive-02-pure-fare-normalizer
    pass  1 claim(s), caveat absent
          normalize_fares llm_backed False
            basis pure-local-computation, pinning_required False
positive-03-vacuous-pass-no-deterministic-annotation
    pass  0 claim(s), caveat absent

6 of 6 reports equal the fixture's own expected block
```

Three passes for three different reasons, and three failures for three.

**The three passes are the three ways a document can be clear.** `positive-01` pins both halves on a
node that needs to. `positive-02` declares a bare `true` on a fare normaliser that calls nothing —
trivially coherent, so the claim is recorded with no pinning obligation and the witness carries no
caveat. `positive-03` declares no determinism at all, and passes with an empty ledger even though
one of its nodes is LLM-backed. Those last two are the property's boundaries, and each has
[its own section](#a-claim-on-a-node-with-no-llm-evidence) below.

**The three failures are one seed defect and two temperature defects.** `negative-01` is the bare
boolean on a node that calls a model. `negative-02` pins a seed and leaves sampling hot at `0.7`.
`negative-03` pins a seed and never mentions temperature. The last two carry the same condition ID
and differ only in their evidence, which is [the next section](#one-condition-two-shapes-of-evidence).

**Note what the evidence line does and does not carry.** The example asks the location model which
of its members are optional rather than listing them, so the line enumerates every *optional*
evidence member P-08 can set and prints the ones actually set. (`annotation` is evidence too, and is
left out here because it is required and therefore always `"deterministic"`; the rendered report
below shows it.) It tests for `is not None`, not for
truthiness, because a legitimately pinned `temperature` of `0` would otherwise disappear from a
transcript claiming to show everything. No failure here sets more than two, because the two
conditions draw on disjoint halves of the model.

The last line matters as much as the rest: every one of the six reports equals the fixture's own
`expected:` block. These are frozen examples the validator is held to in CI, not illustrations
written beside it.

## One condition, two shapes of evidence

`deterministic-llm-temperature-unpinned` covers two documents that read very differently. In one,
the author pinned sampling and pinned it hot. In the other, the author never mentioned sampling and
the provider's default — whatever it is on the day — applies. The specification treats them as one
defect, because a determinism claim is incoherent either way, and the difference survives in the
record rather than in the condition ID.

Read the two evidence lines in the corpus tour above and the distinction is already there.
`negative-02` carries `seed 7; temperature 0.7`: the record shows you the value that has to change.
`negative-03` carries `seed 11` alone: `temperature` is omitted, because the model omits what is
unset and there was nothing to record. So a consumer branching on this condition sees a present
`temperature` when the document named one and no key at all when it did not — the same distinction
the two fixtures were written to pin, and the reason both exist rather than one.

That difference reaches a reader through the record and not through the prose beside it: the
terminal rendering's `declared` line prints exactly these evidence members, so one finding shows a
temperature and the other does not. The `remediation` is the *same text* in both cases, because
there is one closing paragraph per condition and the repair is the same either way — pin it to zero,
or accept that the claim is approximate and drop it.

## A claim on a node with no LLM evidence

C-1 is the first question P-08 asks, and it is answered entirely from the declared effect tags. When
the answer is no, the claim is recorded as trivially coherent and the pinning conditions never run.
Two fixtures show what that record looks like, and the second one is the surprising one.

<!-- gebra:example id=a-claim-on-a-node-with-no-llm-evidence -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import run_property

PROPERTIES = Path(tests.__file__).parent / "fixtures" / "properties"

CASES = (
    ("positive-02", "determinism-replay/positive-02-pure-fare-normalizer", "normalize_fares"),
    ("mixed/10", "mixed/10-all-properties-pass-healthy-research-pipeline", "compose_digest"),
)

for label, relative, node_id in CASES:
    fixture = load_fixture(PROPERTIES / f"{relative}.yaml")
    report = run_property("determinism-replay", fixture.ir)
    declared = next(n for n in fixture.ir.nodes if n.id == node_id).annotations
    spec = declared.deterministic
    form = "bare boolean true" if spec is True else f"object seed={spec.seed}"
    claim = next(c for c in report.witness.claims if c.node == node_id)
    print(f"{label:12} {node_id}")
    print(f"    declares     {form}")
    print(f"    effect       {list(declared.effect or ())} -> llm_backed {claim.llm_backed}")
    print(f"    claim record basis {claim.basis}, pinning_required {claim.pinning_required}")
    print(f"                 seed {claim.seed}, temperature {claim.temperature},")
    print(f"                 divergence_handling {claim.divergence_handling}")
    print(f"    witness      caveat {report.witness.caveat or 'absent'}")
```

<!-- gebra:output id=a-claim-on-a-node-with-no-llm-evidence -->
```text
positive-02  normalize_fares
    declares     bare boolean true
    effect       [] -> llm_backed False
    claim record basis pure-local-computation, pinning_required False
                 seed None, temperature None,
                 divergence_handling None
    witness      caveat absent
mixed/10     compose_digest
    declares     object seed=42
    effect       [] -> llm_backed False
    claim record basis pure-local-computation, pinning_required False
                 seed None, temperature None,
                 divergence_handling None
    witness      caveat absent
```

**The non-LLM claim record is a different shape, not a sparser one.** `basis` says why no obligation
attached — `pure-local-computation` is its only value — and `pinning_required` says the same thing
as a flag a consumer can read without parsing the basis; it is `False` and can be nothing else.
Neither field appears on an LLM-backed record, and none of `seed`, `temperature` or
`divergence_handling` appears on this one.

**`mixed/10` is the case worth remembering: the seed is dropped.** `compose_digest` declares
`deterministic: {seed: 42}`, and the record says `seed None`. That is not a loss of information —
it is the record saying the seed was never part of the question. A node with no declared LLM
evidence has no pinning obligation, so nothing was checked about `42`, and echoing it back would
suggest a verdict about it that P-08 did not reach. If you are looking for a pinned seed in a
report and cannot find it, this is why.

**And the caveat correctly stays away.** Neither witness carries one, because the caveat is about
provider behaviour and neither document declared a provider call. That is the "if and only if" doing
its job in the direction that is easy to get wrong.

The limit under all of this: **`external` and `network` are declarations, not observations.** A node
that calls a model and declares neither tag is, to P-08, pure local computation — its bare
`deterministic: true` is recorded as trivially coherent, and no finding is raised. The declarations
come from `@gebra.contract` or a sidecar, and
[contracts and annotations](../tutorials/contracts-and-annotations.md) is where they are written.
A pass here is only as good as the effect tags the document carries.

## A claim is what P-08 checks, not a node

The other boundary, from the other side. P-08's obligation attaches to a *claim*; a node that makes
none raises nothing, however it is wired and whatever it calls. Two of the three cases have a corpus
fixture, and the third is one edit away from one.

<!-- gebra:example id=a-claim-is-what-p-08-checks -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import WorkflowIR, dump_json, load_json
from gebra.testing import load_fixture
from gebra.verify import run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"
LLM_EVIDENCE = {"network", "external"}

vacuous = load_fixture(CORPUS / "positive-03-vacuous-pass-no-deterministic-annotation.yaml")
witness = run_property("determinism-replay", vacuous.ir).witness
llm_backed = [
    node.id
    for node in vacuous.ir.nodes
    if node.annotations is not None and LLM_EVIDENCE & set(node.annotations.effect or ())
]
print(f"positive-03  LLM-backed nodes {llm_backed}, determinism claims none")
print(f"    witness  kind {witness.kind}, claims {list(witness.claims)},")
print(f"             caveat {witness.caveat or 'absent'}, claim_class {witness.claim_class}")

document = json.loads(
    dump_json(load_fixture(CORPUS / "negative-01-seedless-deterministic-llm-classifier.yaml").ir)
)
print("\nthe same LLM-backed node, three ways of saying something about determinism:")
for label, declared in (
    ("deterministic: true", True),
    ("deterministic: false", False),
    ("no annotation at all", None),
):
    nodes = json.loads(json.dumps(document["nodes"]))
    annotations = next(n for n in nodes if n["id"] == "classify_intent")["annotations"]
    if declared is None:
        annotations.pop("deterministic")
    else:
        annotations["deterministic"] = declared
    verdict = run_property(
        "determinism-replay", load_json(WorkflowIR, json.dumps({**document, "nodes": nodes}))
    )
    if verdict.result == "pass":
        claims = verdict.witness.claims
        detail = f"{len(claims)} claims, caveat {verdict.witness.caveat or 'absent'}"
    else:
        detail = verdict.failure.property_condition
    print(f"    {label:22}{verdict.result}  {detail}")
```

<!-- gebra:output id=a-claim-is-what-p-08-checks -->
```text
positive-03  LLM-backed nodes ['summarize_visa_rules'], determinism claims none
    witness  kind determinism, claims [],
             caveat absent, claim_class heuristic

the same LLM-backed node, three ways of saying something about determinism:
    deterministic: true   fail  deterministic-llm-seed-unpinned
    deterministic: false  pass  0 claims, caveat absent
    no annotation at all  pass  0 claims, caveat absent
```

**The vacuous pass is a real pass with an empty ledger.** `positive-03` has an LLM-backed node in it
and no determinism claim anywhere, so `claims` is the empty tuple and no caveat rides along. The
report says the document made no claim P-08 could find incoherent — which is exactly as much as it
says.

**`deterministic: false` and no annotation at all produce the same report.** The disclaimer is not a
third state in the record: it is a claim about not claiming, and the ledger has nothing to enter for
it. The value of writing it is for the person reading the code, not for this property.

**And the top row is the contrast that makes the point.** One boolean's difference between the first
and the second row moves the same node, in the same graph, with the same declared effects, from a
finding to a clean vacuous pass. Nothing about what the node *does* changed. P-08 checks what the
document claims.

## Two findings, one record

One property reports once. When several claims are incoherent, the deterministically-first finding
fills `failure` and every further same-property finding rides `co_failures`, so nothing is dropped
(§0.3). The corpus has a fixture for this: two analyst branches, both calling a model, both
declaring determinism and neither pinning a seed.

<!-- gebra:example id=two-findings-one-record -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import run_property, to_json

PROPERTIES = Path(tests.__file__).parent / "fixtures" / "properties"

fixture = load_fixture(
    PROPERTIES / "mixed" / "03-parallel-reducerless-key-with-unpinned-llm-writers.yaml"
)
report = run_property("determinism-replay", fixture.ir)
failure = report.failure

print(f"fixture   {fixture.fixture_id}")
print(f"result    {report.result}")
print(f"findings  1 primary + {len(failure.co_failures)} same-property co-finding")
print(to_json(failure))
```

<!-- gebra:output id=two-findings-one-record -->
```text
fixture   mixed/03-parallel-reducerless-key-with-unpinned-llm-writers.yaml
result    fail
findings  1 primary + 1 same-property co-finding
{
  "property_condition": "deterministic-llm-seed-unpinned",
  "location": {
    "kind": "node",
    "node": "market_analysis",
    "annotation": "deterministic",
    "form": "bare-boolean",
    "effects": [
      "network",
      "external"
    ]
  },
  "severity": "warning",
  "claim_class": "heuristic",
  "remediation": "The claim is recorded. Pin the configuration — @gebra.deterministic(seed=N) with temperature=0 — or drop the claim; replay divergence must be logged either way.",
  "co_failures": [
    {
      "property": "determinism-replay",
      "property_condition": "deterministic-llm-seed-unpinned",
      "location": {
        "kind": "node",
        "node": "risk_analysis",
        "annotation": "deterministic",
        "form": "bare-boolean",
        "effects": [
          "network",
          "external"
        ]
      },
      "severity": "warning",
      "claim_class": "heuristic"
    }
  ]
}
```

**Which finding is primary is determined, not chosen.** P-08 walks the nodes in identifier order,
and the first incoherent claim it meets fills `failure`. `market_analysis` precedes `risk_analysis`,
so it leads; there is no severity tie-break to apply here, because every P-08 finding carries the
same severity. Re-run the same document and you get the same primary.

**A co-failure carries its own property, condition, location, severity and claim class** — enough to
act on, and each graded on its own account rather than inheriting the primary's. Both findings here
are `determinism-replay`'s: same-property co-findings name their own property, which is what
distinguishes them from the cross-property advisories that share the field's neighbourhood.

**What a co-failure does not carry is the remediation.** The closing paragraph rides the primary
alone — it is per-condition prose, not per-finding, and repeating it under each entry would add
length and no information. If you are rendering a report, the condition ID on the co-finding is what
tells you which paragraph applies.

!!! note "`mixed/` fixtures answer for more than one property"

    The `expected:` block of a `mixed/` fixture records the whole-run verdict across several
    properties, and `mixed/03`'s is a P-09 `parallel-safety` primary — both branches write one
    reducer-less key — with these two P-08 findings riding it as cross-property **advisories**.
    P-09 is not implemented in this release, so a P-08-scoped run answers for P-08 alone and
    packages both findings under its own primary, which is not the same object as that block. That
    is why the equality check in the corpus tour covers the six single-property fixtures and not
    this one.

## Every finding is a WARNING, and strict mode is the only gate

This is the operational fact about P-08, and it surprises people: a P-08 finding does not fail your
build. Every condition it can emit is WARNING-severity from a HEURISTIC property, so a run whose
only findings are P-08's exits `0` — `pass-with-notes` — and records its snapshot. `--gebra-strict`,
bare or naming this property, is what turns those findings into a gate (§0.2).

<!-- gebra:example id=every-finding-is-a-warning -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import STRICT_OFF, RunPolicy, StrictPolicy, verify

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"

only_p08 = StrictPolicy(mode="per-property", properties=("determinism-replay",))
POLICIES = (("(no flag)", STRICT_OFF), ("--gebra-strict=determinism-replay", only_p08))

records = set()
paths = sorted(CORPUS.glob("negative-*.yaml"))
for path in paths:
    fixture = load_fixture(path)
    print(path.stem)
    for label, strict in POLICIES:
        run = verify(fixture.ir, RunPolicy(strict=strict))
        record = run.outcome_for("determinism-replay").failure
        gate = run.gate
        records.add(
            (record.severity, record.claim_class, gate.counts.blocking, gate.snapshot_eligible)
        )
        promoted = ", ".join(f"{item.property}/{item.origin}" for item in gate.promotions)
        print(f"    {label:34} exit {gate.exit_code}  {gate.outcome:16}", end="")
        print(f" promoted: {promoted or 'nothing'}")

runs = 2 * len(paths)
print(f"\ndistinct (severity, class, blocking findings, snapshot) over {runs} runs: {len(records)}")
for record in sorted(records):
    print(f"  {record}")
```

<!-- gebra:output id=every-finding-is-a-warning -->
```text
negative-01-seedless-deterministic-llm-classifier
    (no flag)                          exit 0  pass-with-notes  promoted: nothing
    --gebra-strict=determinism-replay  exit 1  fail             promoted: determinism-replay/failure
negative-02-seeded-llm-extractor-hot-temperature
    (no flag)                          exit 0  pass-with-notes  promoted: nothing
    --gebra-strict=determinism-replay  exit 1  fail             promoted: determinism-replay/failure
negative-03-seeded-llm-temperature-field-absent
    (no flag)                          exit 0  pass-with-notes  promoted: nothing
    --gebra-strict=determinism-replay  exit 1  fail             promoted: determinism-replay/failure

distinct (severity, class, blocking findings, snapshot) over 6 runs: 1
  ('warning', 'heuristic', 0, True)
```

**The gate moved and the record did not.** The exit code goes from `0` to `1` for each of the three
documents, and the last two lines make the other half mechanical rather than asserting it: the six
runs produced **one** distinct `(severity, claim class, blocking-finding tally, snapshot
eligibility)` tuple between them. A promoted finding keeps `severity: warning` and
`claim_class: heuristic` where it stands, the blocking tally stays at zero, and the run stays
snapshot-eligible — rewriting a HEURISTIC advisory into an ERROR would claim more than the check
supports (§0.2).

**A `Promotion` is a pointer, not a second finding.** It names the owning property and where the
promoted record was carried — here `failure` — and carries no severity or claim class of its own,
because the record it points at still has both. A strict policy naming a different property promotes
nothing; [strict mode](../concepts/what-gebra-checks.md#strict-mode-changes-the-gate-never-the-record)
covers the flag's two forms, and
[verify and interpret](../tutorials/verify-and-interpret.md#strict-mode-moves-the-gate-never-the-record)
runs all four policies over a whole agent.

Practically: leave it off and P-08 is a report your team reads; turn it on for this property and
every unpinned determinism claim has to be pinned or dropped before a merge. Both are defensible
policies, and the report is identical under either.

## The caveat is not decoration

The last two sections were the record. This one is what a person sees, because the caveat is the
part of a P-08 pass most likely to be skimmed past, and it is the part that keeps the result honest.

<!-- gebra:example id=the-caveat-in-a-rendered-report -->
```python
from pathlib import Path

import tests
from gebra.report import TerminalOptions, render_human
from gebra.testing import load_fixture
from gebra.verify import verify

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"
TERMINAL = TerminalOptions(color=False, width=96)


def block(rendering, heading):
    """One section of the rendered report — its blocks are separated by blank lines."""
    for section in rendering.split("\n\n"):
        if section.startswith(heading):
            return section
    raise LookupError(heading)


for name in (
    "positive-01-pinned-seed-zero-temp-classifier",
    "negative-01-seedless-deterministic-llm-classifier",
):
    run = verify(load_fixture(CORPUS / f"{name}.yaml").ir)
    print(block(render_human(run, TERMINAL), "P-08 determinism-replay"))
    print(f"  gate                    exit {run.gate.exit_code}, {run.gate.outcome}")
    print()
```

<!-- gebra:output id=the-caveat-in-a-rendered-report -->
```text
P-08 determinism-replay — pass  [HEURISTIC]
  witness                 1 declared determinism claim | provider caveat carried
    claim class             heuristic (carried in-band)
    claims                  1 declared claim
    claim                   classify_request — LLM-backed | pinned seed 42 | pinned temperature 
0.0 | divergence handling logged
    caveat                  provider-seed-reproducibility-not-guaranteed
  gate                    exit 0, pass

P-08 determinism-replay — fail  (1 finding: 1 warning)
  warning: deterministic-llm-seed-unpinned  [P-08 determinism-replay | HEURISTIC]
    node                    classify_intent
    declared                annotation deterministic | form bare-boolean | effects network, 
external
    finding                 Determinism declared on an LLM-backed node with no pinned seed
    remediation             The claim is recorded. Pin the configuration — 
@gebra.deterministic(seed=N) with temperature=0 — or drop the claim; replay divergence must be 
logged either way.
  gate                    exit 0, pass-with-notes
```

Every line there came from a structure earlier on this page: the summary line counts `claims` and
reports whether `caveat` is set, the `claim` line is one `DeterminismClaim` rendered, and the
`declared` line is the location's evidence members. `[HEURISTIC]` beside the pass is the property's
class, because a pass carries no per-record grade; `[P-08 determinism-replay | HEURISTIC]` beside
the finding is the record's own. The width is the only thing set by hand — a real terminal supplies
its own — and the wrapping is what a 96-column one does.

Two things are worth reading twice. The pass **displays the caveat**, in the same block and at the
same level as the pinned seed — the summary line names it before the detail lines are reached, so a
reader who stops at the first line has still met it. And the second block is a **fail** whose gate
line says `exit 0`, which is
[the previous section](#every-finding-is-a-warning-and-strict-mode-is-the-only-gate) as a reader
meets it. [Verify and interpret](../tutorials/verify-and-interpret.md#the-report-a-person-reads)
walks the whole rendering.

## What P-08 reads

`nodes[].id`, `nodes[].annotations.deterministic` and `nodes[].annotations.effect`. That is the
whole list — three fields, all on nodes. `edges[]`, `state` and `runtime` are not read, and neither
is any other annotation slot. The specification says so as a negative requirement rather than as a
description (§8.3, §8.7), and the check below is that requirement executed.

<!-- gebra:example id=what-p-08-reads -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import Annotations, WorkflowIR, dump_json, load_json
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"

# Asked of the model, never listed: every annotation slot except the two P-08 reads.
READ = {"deterministic", "effect"}
DROPPED = tuple(sorted(set(Annotations.model_fields) - READ))

fixture = load_fixture(CORPUS / "positive-01-pinned-seed-zero-temp-classifier.yaml")
document = json.loads(dump_json(fixture.ir))

changed = [f'every state field rewritten to "object" ({len(document["state"])} keys)']
for key in document["state"]:
    document["state"][key] = {"type": "object"}
changed.append(f"all {len(document['edges'])} edges deleted")
document["edges"] = []
for node in document["nodes"]:
    for member in DROPPED:
        if node["annotations"].pop(member, None) is not None:
            changed.append(f"{node['id']}.annotations.{member}")

before = run_property("determinism-replay", fixture.ir)
after = run_property("determinism-replay", load_json(WorkflowIR, json.dumps(document)))

print(f"changed   {len(changed)} things P-08 does not read:")
for member in changed:
    print(f"            {member}")
print(f"dropped   all {len(DROPPED)} annotation slots that are not one of {sorted(READ)}")
print("kept      nodes[].id, annotations.deterministic and annotations.effect")
print(f"verdicts  {before.result} before, {after.result} after")
print(f"reports equal: {models_equivalent(before, after)}")
```

<!-- gebra:output id=what-p-08-reads -->
```text
changed   10 things P-08 does not read:
            every state field rewritten to "object" (4 keys)
            all 2 edges deleted
            receive_request.annotations.input
            receive_request.annotations.output
            receive_request.annotations.pure
            classify_request.annotations.input
            classify_request.annotations.output
            plan_itinerary.annotations.input
            plan_itinerary.annotations.output
            plan_itinerary.annotations.pure
dropped   all 12 annotation slots that are not one of ['deterministic', 'effect']
kept      nodes[].id, annotations.deterministic and annotations.effect
verdicts  pass before, pass after
reports equal: True
```

**The graph is gone and the report is unchanged.** Every edge deleted, every state field retyped,
and every one of the twelve annotation slots that is not `deterministic` or `effect` dropped — and
the witness is the same value, pinned seed and mandatory caveat included. The slot list is asked of
the annotation model rather than written out here, so a future additive slot joins the sweep instead
of quietly sitting outside it. That the report survives all of it is not an incidental property: it
is why P-08 costs one pass over the nodes and why its result has no topology precondition, which is
the next section.

**One consequence for reading a finding.** Where a node sits, how often it runs and whether anything
loops back to it are all outside what P-08 asks. A determinism claim on a node inside a retry loop
and the same claim on a node reached once are the same finding, because the incoherence is in the
declaration and not in the wiring. The property that asks about re-execution is
[P-06 `effect-safety`](p06-effect-safety.md), and it answers separately.

## The P-01 boundary does not reach P-08

The topology-consuming validators have results defined **only over P-01-clean topology**, and on a
graph that fails P-01 their answers are best-effort diagnostics rather than contract-bearing
verdicts (§0.3). P-08 is not one of them, and a run says so itself.

<!-- gebra:example id=the-p-01-boundary-does-not-reach-p-08 -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import WorkflowIR, dump_json, load_json
from gebra.testing import load_fixture
from gebra.verify import TOPOLOGY_SLUGS, models_equivalent, verify

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "determinism-replay"

fixture = load_fixture(CORPUS / "negative-01-seedless-deterministic-llm-classifier.yaml")
document = json.loads(dump_json(fixture.ir))
broken = {
    **document,
    "edges": [
        *document["edges"],
        {
            "from": "compose_response",
            "kind": "conditional",
            "condition": "'again' if intent == 'unclear' else 'done'",
            "path_map": {"again": "classfy_intent", "done": "compose_response"},
        },
    ],
}

print(f"properties scoped to P-01-clean topology: {list(TOPOLOGY_SLUGS)}")
answers = []
for label, ir in (
    ("as vendored", fixture.ir),
    ("one typo in a path_map", load_json(WorkflowIR, json.dumps(broken))),
):
    run = verify(ir)
    answer = run.outcome_for("determinism-replay")
    answers.append(answer)
    p01 = run.outcome_for("graph-well-formed")
    named = f"  {p01.failure.property_condition}" if p01.result == "fail" else ""
    print(f"\n{label}")
    print(f"    gate                exit {run.gate.exit_code}, {run.gate.outcome}")
    print(f"    best_effort         {list(run.best_effort)}")
    print(f"    graph-well-formed   {p01.result}{named}")
    print(f"    determinism-replay  {answer.result}  {answer.failure.property_condition}")

print(f"\nthe two P-08 answers are the same value: {models_equivalent(*answers)}")
```

<!-- gebra:output id=the-p-01-boundary-does-not-reach-p-08 -->
```text
properties scoped to P-01-clean topology: ['termination-witness', 'dataflow-completeness', 'effect-safety']

as vendored
    gate                exit 0, pass-with-notes
    best_effort         []
    graph-well-formed   pass
    determinism-replay  fail  deterministic-llm-seed-unpinned

one typo in a path_map
    gate                exit 1, fail
    best_effort         ['termination-witness', 'dataflow-completeness', 'effect-safety']
    graph-well-formed   fail  path-map-target-undefined
    determinism-replay  fail  deterministic-llm-seed-unpinned

the two P-08 answers are the same value: True
```

One typo in a `path_map` label breaks the graph: P-01 reports `path-map-target-undefined`, the gate
fails on that FATAL, and three properties' answers become qualified. **P-08's does not.** Its report
is the same value on both documents, because the edge it would have had to read is one it never
reads.

That is a small thing, and it is worth stating plainly: on a run where P-01 failed, a P-06 pass
is [not a verdict](p06-effect-safety.md#the-p-01-boundary), and a P-08 finding still is. It is
also the reason `determinism-replay` never appears in `best_effort` — the field is populated from a
fixed list of the three topology-consuming properties, and P-08 is not on it.

## What a pass does not claim

This is the section the property exists for. A P-08 pass says that every determinism claim in a
document is coherent with the effect tags declared beside it — a statement about two annotation
slots, and about nothing else. Six things stay firmly on the far side of that line.

* **A pinned seed is a declaration, not a provider's behaviour.** Determinism of an external model
  is a runtime phenomenon of the world, and the IR carries no fact about it. The specification's
  Appendix B carries a dated, deliberately non-normative survey of provider classes for exactly this
  reason: its strongest class is bit-for-bit repetition only under a fully pinned stack, its weakest
  is a documented disclaimer, and provider behaviour is provider-mutable, so the class never moves
  the verdict — only, at most, the wording of a warning. `seed 42, temperature 0` in a witness means
  the document said so.
* **`divergence_handling: "logged"` is a policy echo with no IR carrier.** It is a constant, set on
  every coherent LLM-backed claim, and it restates an obligation rather than reporting a fact: no
  field of the document was read to produce it, and it is not evidence that any divergence is logged
  anywhere. Keeping it in the witness was ruled explicitly (DEC-14) so the obligation travels with
  the claim; reading it as a finding about your runtime would be the mistake it is easiest to make
  on this page.
* **`llm_backed: false` means "no LLM evidence was declared".** It is not a finding that the node
  makes no model call. A node that calls one and declares neither `external` nor `network` is
  recorded as `pure-local-computation`, and P-08 raises nothing — which makes the accuracy of your
  effect tags part of what this pass rests on.
* **An empty ledger is not a clean bill of health.** The vacuous pass says the document declared no
  determinism, and that is all it says. A workflow full of unclaimed model calls passes P-08
  trivially, because P-08 checks claims.
* **The claim class is HEURISTIC, and that is not a hedge.** It is the honest label for an advisory
  lint with no proof obligation behind it. Every finding carries it, every co-finding carries it,
  and a strict policy that turns a finding into a gate leaves it exactly where it was.
* **The neighbouring runtime question is nobody's here.** Whether two runs of your agent actually
  produce the same output is an observation about executions, and gebra never executes a workflow —
  observing a running agent is a different tool's job, and the specification says so rather than
  leaving the gap implied.

So the reading of a P-08 pass is "every determinism claim in this document pins what a claim of that
kind has to pin", and the reading of a failure is "here is a claim that does not, and here is the
half that is missing" — a statement about the declarations in front of you, not a prediction about a
run. That is still worth having: an unpinned determinism claim on a model call is a promise nothing
in the definition backs, and a document is a much cheaper place to notice that than a replay that
came back different.

One further limit worth keeping straight, and it is the one place the topology-independence above
runs out: this build's validators are defined over `ir_version` 1.0, and a document stamped 1.1 —
which is what using the `dynamic` edge kind does to it — reaches
[no verdict at all](../tutorials/extract-your-first-ir.md#one-consequence-to-know-before-you-build-on-this),
exit `2`. The refusal is on the declared version, not on the edge, so it takes P-08 with it even
though P-08 would never have read that edge.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking a
runnable, resolving a hostname or opening a connection all raise. The output blocks are what those
runs printed, and three of them additionally re-check whole reports against the corpus's own frozen
`expected:` blocks — eight reports in all —
[executable examples](../contributing/executable-examples.md) explains the mechanism.

The frozen contract behind this page is PROPERTY-CATALOG-SPEC §8 and Appendix B with the shared
envelope of §0; the shapes it pins were ratified in decision record DEC-11 (the witness and failure
forms), with DEC-14 ruling that `divergence_handling` stays in the witness as a policy echo and
DEC-16 authorizing the two gap fixtures this page's corpus tour runs.
`gebra.verify.properties.determinism_replay` and its tests are where that contract is implemented
and pinned in this repository. This is the last of the five per-validator explainers; the others are
[P-01 `graph-well-formed`](p01-graph-well-formed.md),
[P-02 `termination-witness`](p02-termination-witness.md),
[P-04 `dataflow-completeness`](p04-dataflow-completeness.md) and
[P-06 `effect-safety`](p06-effect-safety.md).
