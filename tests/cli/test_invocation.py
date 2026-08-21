"""The pre-parse strict reading — CLI-SPEC §3.3's grammar, off the raw tokens (CLI-04).

The load-bearing claim is negative space: a bare ``--strict`` followed by a target must
**not** swallow the target as its value, which is exactly what an optional-value option in
the parser would do. Everything §3.3 fixes — the ``=``-attached value form, the
``--gebra-strict`` exact alias, the one-flag rule, the unrecognized-slug refusal with its
§5.4 suggestion — is asserted here at the unit level; ``tests/cli/test_verify.py`` holds
the same rules through the whole entry point.
"""

from __future__ import annotations

from gebra.cli.invocation import read_invocation
from gebra.verify import PROPERTY_SLUGS

# ── The two forms, both spellings ────────────────────────────────────────────────────────


def test_bare_strict_promotes_everything_and_never_swallows_the_target() -> None:
    invocation = read_invocation(["verify", "--strict", "workflow.ir.yaml"])
    assert invocation.strict.policy is not None
    assert invocation.strict.policy.mode == "all"
    assert invocation.strict.problems == ()
    assert invocation.argv == ("verify", "workflow.ir.yaml")


def test_attached_value_selects_the_named_properties_in_order_verbatim() -> None:
    invocation = read_invocation(
        ["verify", "--strict=determinism-replay,effect-safety", "workflow.ir.yaml"]
    )
    policy = invocation.strict.policy
    assert policy is not None
    assert policy.mode == "per-property"
    assert policy.properties == ("determinism-replay", "effect-safety")


def test_gebra_strict_is_an_exact_alias_in_both_forms() -> None:
    bare = read_invocation(["verify", "--gebra-strict", "w.yaml"])
    assert bare.strict.policy is not None and bare.strict.policy.mode == "all"
    valued = read_invocation(["verify", "--gebra-strict=graph-well-formed", "w.yaml"])
    assert valued.strict.policy is not None
    assert valued.strict.policy.properties == ("graph-well-formed",)


def test_a_duplicate_slug_is_recorded_verbatim_not_deduplicated() -> None:
    """§3.3: the policy in force is recorded as given."""
    invocation = read_invocation(["verify", "--strict=effect-safety,effect-safety", "w.yaml"])
    assert invocation.strict.policy is not None
    assert invocation.strict.policy.properties == ("effect-safety", "effect-safety")


# ── The one-flag rule ────────────────────────────────────────────────────────────────────


def test_both_spellings_together_are_a_usage_problem_not_a_double_promotion() -> None:
    invocation = read_invocation(["verify", "--strict", "--gebra-strict", "w.yaml"])
    assert invocation.strict.policy is None
    assert len(invocation.strict.problems) == 1
    assert "one flag" in invocation.strict.problems[0]
    assert "--strict" in invocation.strict.problems[0]
    assert "--gebra-strict" in invocation.strict.problems[0]


def test_the_same_spelling_twice_is_the_same_usage_problem() -> None:
    invocation = read_invocation(["verify", "--strict=effect-safety", "--strict", "w.yaml"])
    assert invocation.strict.policy is None
    assert invocation.strict.problems


# ── Value refusals ───────────────────────────────────────────────────────────────────────


def test_an_empty_value_names_no_property_and_is_refused() -> None:
    invocation = read_invocation(["verify", "--strict=", "w.yaml"])
    assert invocation.strict.policy is None
    assert "names no property" in invocation.strict.problems[0]


def test_an_empty_slug_between_commas_is_refused() -> None:
    invocation = read_invocation(["verify", "--strict=effect-safety,,graph-well-formed", "w.yaml"])
    assert invocation.strict.policy is None
    assert any("empty property slug" in problem for problem in invocation.strict.problems)


def test_an_unrecognized_slug_is_refused_with_a_suggestion() -> None:
    """§3.3: never a silently ignored name; §5.4: a did-you-mean over the closed slugs."""
    invocation = read_invocation(["verify", "--strict=determinism-repla", "w.yaml"])
    assert invocation.strict.policy is None
    (problem,) = invocation.strict.problems
    assert "'determinism-repla' is not a property slug" in problem
    assert "Did you mean determinism-replay?" in problem


def test_every_catalog_slug_is_accepted() -> None:
    for slug in PROPERTY_SLUGS:
        invocation = read_invocation(["verify", f"--strict={slug}", "w.yaml"])
        assert invocation.strict.policy is not None, slug
        assert invocation.strict.policy.properties == (slug,)


# ── Scope: after the verb, before `--` ───────────────────────────────────────────────────


def test_tokens_before_the_verb_are_left_for_the_application_parser() -> None:
    """A pre-verb ``--strict`` is an unknown application-level option, not a policy."""
    invocation = read_invocation(["--strict", "verify", "w.yaml"])
    assert invocation.strict.policy is None
    assert invocation.strict.tokens == ()
    assert invocation.argv == ("--strict", "verify", "w.yaml")


def test_tokens_after_the_separator_are_targets_not_flags() -> None:
    """§1.2: ``--`` ends option parsing, so a target spelled ``--strict`` stays addressable."""
    invocation = read_invocation(["verify", "--", "--strict"])
    assert invocation.strict.policy is None
    assert invocation.strict.tokens == ()
    assert invocation.literal_targets == ("--strict",)
    assert invocation.argv == ("verify", "--", "--strict")


def test_a_prefix_lookalike_is_not_a_strict_token() -> None:
    """``--strictly`` belongs to the unknown-option scan, not to the strict reading."""
    invocation = read_invocation(["verify", "--strictly", "w.yaml"])
    assert invocation.strict.tokens == ()
    assert "--strictly" in invocation.argv


def test_an_invocation_with_no_verb_reads_nothing() -> None:
    invocation = read_invocation(["--version"])
    assert invocation.argv == ("--version",)
    assert invocation.strict.tokens == ()
