"""The corpus-wide validity claim — CLI-06's acceptance box, exercised in full.

Every IR block the vendored corpus carries (every fixture; the P-12 pairs contribute two
each) is rendered twice — plain, and overlaid with its own ``verify()`` run — and every
emission is parse-checked by the guide's §9 conformance checker, which refuses any
construct outside the licensed subset rather than skipping it. Beside validity, the
rendered text is swept with the TE-15 banned-phrase list through the lint's own loader,
because a phrase composed at render time would pass a source-file scan (the CLI-03
precedent, applied to this card's surface).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gebra.display import render_mermaid
from gebra.ir import WorkflowIR
from gebra.testing import load_fixture
from gebra.verify import verify
from tests._corpus import census
from tools.honest_claims_lint import load_phrases
from tools.mermaid_check import mermaid_problems

FIXTURES = Path(__file__).parent.parent / "fixtures" / "properties"

PHRASES = load_phrases(Path(__file__).parent.parent.parent / "tools" / "honest-claims-phrases.txt")


def _corpus_irs() -> list[tuple[str, WorkflowIR]]:
    cases: list[tuple[str, WorkflowIR]] = []
    for path in sorted(FIXTURES.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        fixture = load_fixture(path)
        for attribute in ("ir", "ir_before", "ir_after"):
            ir = getattr(fixture, attribute, None)
            if ir is not None:
                cases.append((f"{path.relative_to(FIXTURES)}::{attribute}", ir))
    return cases


CASES = _corpus_irs()


def test_the_corpus_is_the_size_the_claim_needs() -> None:
    """Every fixture the provenance manifest lists, every one contributing its IR blocks —
    the sweep below is not quietly running over a partial or empty parametrization."""
    files = {label.split("::")[0].replace("\\", "/") for label, _ in CASES}
    assert files == set(census().fixture_ids)
    assert len(CASES) == census().ir_blocks


@pytest.mark.parametrize(("name", "ir"), CASES, ids=[name for name, _ in CASES])
def test_every_corpus_ir_emits_valid_mermaid_plain_and_overlaid(name: str, ir: WorkflowIR) -> None:
    plain = render_mermaid(ir, source=f"{name} (ir-document)")
    assert mermaid_problems(plain) == []

    report = verify(ir)
    assert report.gate.exit_code != 2, f"{name}: the corpus run reached no verdict"
    overlaid = render_mermaid(ir, report=report, source=f"{name} (ir-document)")
    assert mermaid_problems(overlaid) == []

    for text in (plain, overlaid):
        lowered = text.lower()
        for phrase in PHRASES:
            assert phrase not in lowered, f"{name}: rendered output carries {phrase!r}"
