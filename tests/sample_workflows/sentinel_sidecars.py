"""Sidecar fixtures for the ANNOTATION-API-SPEC §2 loader and its tripwire (WA-07).

One table, :data:`SIDECAR_FIXTURES`, fully specifying each file's outcome: whether the file is
*loaded* (§2's file-level rules) and which §2 rules its contents violate, in file order. A
single table rather than a "good" and a "bad" one, because §2's grades do not split that way —
a file can be loaded and still have half its slots rejected, which is the whole point of
warning-grade validation.

Several fixtures are hostile in ways the loader must survive without executing anything: a
table key that reads like an expression, TOML's two value kinds JSON has no form for (the
date/time family and non-finite floats), bytes that are not a UTF-8 document, nesting deep
enough to exhaust the parser's stack, nesting deep enough to exceed the ``args_schema`` depth
bound without exhausting it, and integers on both sides of the I-JSON exact range that
IR-SPEC §6.3 fixes for the canonical form. None of them is a value the loader may call,
render, or coerce, and none of them may make ``extract()`` raise.

The node ids the well-keyed entries use are the sentinel graph's (``plan_step``, ``act_step``,
``summarize_step``), so an extraction over :mod:`tests.sample_workflows.sentinel_graph` can
tell a matched key from a stale one.

Nothing here imports langgraph, opens a socket, or executes anything: the module is TOML text
plus one file-writing helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

#: The one accepted schema value, spelled out here rather than imported from the loader: a
#: fixture that derived it from the code could not catch the code changing it.
SCHEMA_LINE: Final = 'schema = "gebra-sidecar-v1"'

#: The node ids of ``tests.sample_workflows.sentinel_graph``, which the keyed fixtures use.
SENTINEL_NODE_IDS: Final[tuple[str, ...]] = ("act_step", "plan_step", "summarize_step")

#: ``café_step`` precomposed (NFC) and decomposed (NFD). The §5.1 grammar admits the first as
#: a node id and refuses the second, so the pair is what makes "keys are compared as escaped
#: bytes, after NFC" observable rather than asserted.
NFC_KEY: Final = "caf\u00e9_step"
NFD_KEY: Final = "cafe\u0301_step"


@dataclass(frozen=True)
class SidecarFixture:
    """One sidecar file and the outcome §2 fixes for it.

    Attributes:
        text: The file's contents — ``str`` for the ordinary case, and ``bytes`` where the
            point of the fixture is bytes that are *not* a UTF-8 document. The second form
            exists because a table that could only hold text could not express the input that
            reaches the parser's decode step, and every claim quantified over this table
            would silently exclude it.
        loaded: Whether the file is loaded at all — i.e. whether the reading records its
            path. §2's file-level rules (``schema``, and the readability the same sentence's
            grade covers) are the only things that make this ``False``.
        rules: The :class:`~gebra.annotations.sidecar.SidecarRule` values the reading must
            report, in file order, as plain strings — written out here rather than imported,
            so the expectation is the fixture's and not the code's.
        entries: The entry keys the reading must carry, in file order. An entry survives its
            own slot rejections: the key is what §2's unmatched-key rule is about.
    """

    text: str | bytes
    loaded: bool
    rules: tuple[str, ...] = ()
    entries: tuple[str, ...] = ()


#: A sidecar declaring all nine annotatable slots on one node — the §2 example's vocabulary,
#: in the §1 keyword spellings the example itself writes.
NINE_SLOTS: Final = f"""
{SCHEMA_LINE}

[nodes.plan_step]
reads         = ["query", "budget"]
writes        = ["plan"]
effects       = ["network", "billable"]
pure          = false
idempotent    = {{ key = "plan" }}
deterministic = {{ seed = 7, temperature = 0 }}
variant       = {{ key = "remaining", measure = "len" }}
compensation  = {{ hook = "act_step" }}

[nodes.plan_step.args_schema]
type = "object"
required = ["query"]

[nodes.plan_step.args_schema.properties.query]
type = "string"
"""

SIDECAR_FIXTURES: Final[dict[str, SidecarFixture]] = {
    # ── Loaded, nothing rejected ─────────────────────────────────────────────────────────
    "nine_slots": SidecarFixture(NINE_SLOTS, loaded=True, entries=("plan_step",)),
    "schema_only": SidecarFixture(f"{SCHEMA_LINE}\n", loaded=True),
    "empty_nodes_table": SidecarFixture(f"{SCHEMA_LINE}\n[nodes]\n", loaded=True),
    "multi_segment_key": SidecarFixture(
        f"""
{SCHEMA_LINE}

[nodes."research/tools/web_search"]
effects       = ["network"]
deterministic = {{ seed = 7, temperature = 0.0 }}
""",
        loaded=True,
        entries=("research/tools/web_search",),
    ),
    "escaped_separator_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."summarize%2Fmerge"]\npure = true\n',
        loaded=True,
        entries=("summarize%2Fmerge",),
    ),
    "escaped_marker_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."100%25_certain"]\npure = true\n',
        loaded=True,
        entries=("100%25_certain",),
    ),
    # A key that reads like code. It is a perfectly good node id under IR-SPEC §5.1 (no `/`,
    # no `%`), so the loader keys on it verbatim and it matches nothing — it is never
    # evaluated, and the tripwire is what says so rather than this comment.
    "expression_shaped_key": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.\"__import__('os').system('echo tripped')\"]\npure = true\n",
        loaded=True,
        entries=("__import__('os').system('echo tripped')",),
    ),
    "nfc_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."{NFC_KEY}"]\npure = true\n',
        loaded=True,
        entries=(NFC_KEY,),
    ),
    "deep_args_schema": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.act_step]\n"
        'args_schema = { a = { b = { c = { d = { e = { f = "leaf" } } } } } }\n',
        loaded=True,
        entries=("act_step",),
    ),
    # The largest seed the canonical form can carry exactly, ±(2**53−1) per IR-SPEC §6.3.
    "largest_exact_seed": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.act_step]\ndeterministic = {{ seed = 9007199254740991 }}\n",
        loaded=True,
        entries=("act_step",),
    ),
    # One past it. TOML's own integer range is 64-bit, so this is an ordinary thing to write
    # and an impossible thing to digest — the slot is rejected rather than carried into an IR
    # that would raise at `graph_version()` time.
    "out_of_range_seed": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.act_step]\ndeterministic = {{ seed = 9007199254740992 }}\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("act_step",),
    ),
    "out_of_range_args_schema_integer": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.act_step]\nargs_schema = {{ maximum = 9223372036854775807 }}\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("act_step",),
    ),
    "empty_effects_is_a_declaration": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.act_step]\neffects = []\n",
        loaded=True,
        entries=("act_step",),
    ),
    # ── Not loaded at all: §2's file-level rules ─────────────────────────────────────────
    "no_schema": SidecarFixture(
        "[nodes.plan_step]\npure = true\n", loaded=False, rules=("schema-missing",)
    ),
    "wrong_schema": SidecarFixture(
        'schema = "gebra-sidecar-v2"\n[nodes.plan_step]\npure = true\n',
        loaded=False,
        rules=("schema-unknown",),
    ),
    "non_string_schema": SidecarFixture(
        "schema = 1\n[nodes.plan_step]\npure = true\n", loaded=False, rules=("schema-unknown",)
    ),
    "unparsable": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step\npure = true\n",
        loaded=False,
        rules=("file-unparsable",),
    ),
    "not_toml_at_all": SidecarFixture(
        "\x00\x01 this is not a TOML document \x00\n", loaded=False, rules=("file-unparsable",)
    ),
    # The parser decodes as UTF-8 *before* it parses, so this fails with a `UnicodeDecodeError`
    # rather than a `TOMLDecodeError` — a different branch, and the reason this table has to be
    # able to hold bytes at all. (`café` in latin-1; `\xe9` is not a UTF-8 start byte.)
    "not_utf8": SidecarFixture(
        b'schema = "gebra-sidecar-v1"\n# caf\xe9\n', loaded=False, rules=("file-unparsable",)
    ),
    # The parser recurses on nested arrays, so a deep enough one exhausts the stack —
    # a `RecursionError`, which is neither of the two failures above. A sidecar may be
    # generated, merged or hostile, and "extraction stays total" has to hold for all three.
    "pathological_nesting": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\nargs_schema = {{ x = "
        + "[" * 2000
        + "]" * 2000
        + " }\n",
        loaded=False,
        rules=("file-unparsable",),
    ),
    # ── Loaded, with the file- or entry-level rejections §2 names ────────────────────────
    "unknown_file_key": SidecarFixture(
        f"{SCHEMA_LINE}\nnodez = {{ }}\n[nodes.plan_step]\npure = true\n",
        loaded=True,
        rules=("file-key-unknown",),
        entries=("plan_step",),
    ),
    "nodes_not_a_table": SidecarFixture(
        f'{SCHEMA_LINE}\nnodes = "plan_step"\n', loaded=True, rules=("nodes-table-invalid",)
    ),
    "entry_not_a_table": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes]\nplan_step = 5\n", loaded=True, rules=("entry-not-a-table",)
    ),
    "reserved_entry_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."__end__"]\npure = true\n',
        loaded=True,
        rules=("entry-key-not-a-node-id",),
    ),
    "unescaped_separator_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."a//b"]\npure = true\n',
        loaded=True,
        rules=("entry-key-not-a-node-id",),
    ),
    "bad_escape_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."half%off"]\npure = true\n',
        loaded=True,
        rules=("entry-key-not-a-node-id",),
    ),
    "nfd_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes."{NFD_KEY}"]\npure = true\n',
        loaded=True,
        rules=("entry-key-not-a-node-id",),
    ),
    "unknown_slot_key": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\nretry_policy = 3\n",
        loaded=True,
        rules=("slot-key-unknown",),
        entries=("plan_step",),
    ),
    "ir_spelled_slot_key": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\ninput = ["query"]\n',
        loaded=True,
        rules=("slot-key-unknown",),
        entries=("plan_step",),
    ),
    "unknown_effect_tag": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\neffects = ["network", "teleport"]\n',
        loaded=True,
        rules=("effect-tag-unknown",),
        entries=("plan_step",),
    ),
    "every_effect_tag_unknown": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\neffects = ["teleport"]\n',
        loaded=True,
        rules=("effect-tag-unknown",),
        entries=("plan_step",),
    ),
    "pure_with_effects": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\npure = true\neffects = ["network"]\n',
        loaded=True,
        rules=("pure-effect-exclusive",),
        entries=("plan_step",),
    ),
    "deterministic_without_seed": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\ndeterministic = {{ temperature = 0.0 }}\n",
        loaded=True,
        rules=("deterministic-seed-required",),
        entries=("plan_step",),
    ),
    "bare_string_reads": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\nreads = "budget"\n',
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "non_string_state_key": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\nreads = [1, 2]\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "non_boolean_pure": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\npure = "yes"\n',
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "date_valued_slot": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\nargs_schema = {{ x = 2026-08-02 }}\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "non_finite_temperature": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\ndeterministic = {{ seed = 1, temperature = nan }}\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    # Nesting the parser survives but the `args_schema` depth bound does not admit: the file
    # loads, the slot is rejected. The pair with `deep_args_schema` is what makes the bound
    # reachable from this surface rather than only from the decorator's.
    "over_deep_args_schema": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\nargs_schema = "
        + "{ a = " * 70
        + '"leaf"'
        + " }" * 70
        + "\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    # A TOML inline table where a list of state keys belongs. It is **accepted**, as its keys,
    # and the acceptance is deliberate rather than an oversight: §1 types the slot
    # `Iterable[str]`, a mapping is one, and reading it as its keys is a coherent thing to have
    # meant — the same call EX-08 recorded when it declined to refuse a `dict` passed to
    # `reads=`. The fixture exists so the behaviour is visible and would have to be changed on
    # purpose. (A bare *string* is refused, because six one-character state keys is not.)
    "inline_table_reads": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\nreads = {{ budget = 1 }}\n",
        loaded=True,
        entries=("plan_step",),
    ),
    "bare_string_effects": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\neffects = "network"\n',
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "non_finite_scalar_slot": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\npure = nan\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "variant_not_a_table": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\nvariant = "loop"\n',
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "compensation_without_hook": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.plan_step]\ncompensation = {{ }}\n",
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "variant_without_measure": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\nvariant = {{ key = "n" }}\n',
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "compensation_not_a_table": SidecarFixture(
        f'{SCHEMA_LINE}\n[nodes.plan_step]\ncompensation = "act_step"\n',
        loaded=True,
        rules=("slot-value-invalid",),
        entries=("plan_step",),
    ),
    "date_valued_unknown_key": SidecarFixture(
        f"{SCHEMA_LINE}\n[nodes.act_step]\nreleased_on = 2026-08-02\n",
        loaded=True,
        rules=("slot-key-unknown",),
        entries=("act_step",),
    ),
}

#: The fixtures whose file is loaded, and those whose file is not — derived, so the two can
#: never disagree with :data:`SIDECAR_FIXTURES`.
LOADED_SIDECARS: Final[dict[str, SidecarFixture]] = {
    name: fixture for name, fixture in SIDECAR_FIXTURES.items() if fixture.loaded
}
NOT_LOADED_SIDECARS: Final[dict[str, SidecarFixture]] = {
    name: fixture for name, fixture in SIDECAR_FIXTURES.items() if not fixture.loaded
}


def write_sidecar(directory: Path, text: str | bytes, *, name: str = "gebra.toml") -> Path:
    """Write ``text`` into ``directory`` as a sidecar file and return its path.

    Always written as bytes rather than through text mode: TOML is UTF-8 by definition, a
    fixture that picked up the platform's newline translation would fail differently on
    different machines, and a fixture whose whole point is *not* being UTF-8 could not go
    through an encoder at all.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    return path
