"""The round-trip operation itself — build, extract, compare against the fixture.

One function does the work (:func:`round_trip`) and one value carries the result
(:class:`RoundTrip`). The comparison is IR-SPEC §1.2's extractor-conformance operation with a
fixture in the golden's place: canonical bytes byte-identical, ``graph_version`` string-equal.

**The structural diff renders failures; it never decides them.** :meth:`RoundTrip.report`
walks the two canonical JSON documents and names what differs, so a red pair says *which
node's ``effect`` slot* or *which edge* moved rather than printing two blobs. The verdict is
:attr:`RoundTrip.matched`, which is bytes equality and nothing else; ``test_round_trip.py``
holds it to §1.2's sentence directly, by substituting one byte at **every** position of a
green pair's canonical form and requiring the comparison to reject each one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gebra.extraction import extract
from gebra.ir import canonical_bytes, graph_version

if TYPE_CHECKING:
    from gebra.extraction import ExtractionWarning
    from gebra.ir import WorkflowIR
    from tests.drift.pairs import DriftPair

__all__ = ["RoundTrip", "diff_documents", "round_trip"]


@dataclass(frozen=True)
class RoundTrip:
    """What one pair's round trip observed.

    Attributes:
        pair: The pair this is the result of.
        extracted: The IR ``gebra.extract()`` produced from the mini builder script.
        fixture: The IR block the vendored fixture carries.
        extracted_bytes: ``canonical_bytes(extracted)`` — IR-SPEC §6.1 steps 2–6.
        fixture_bytes: ``canonical_bytes(fixture)``, the same operation on the corpus side.
        warnings: The extraction warnings, in emission order. Expected empty (§8's
            strict-mode bar) — see the package docstring.
    """

    pair: DriftPair
    extracted: WorkflowIR
    fixture: WorkflowIR
    extracted_bytes: bytes
    fixture_bytes: bytes
    warnings: tuple[ExtractionWarning, ...]

    @property
    def matched(self) -> bool:
        """Whether the canonical forms are byte-identical — the whole verdict."""
        return self.extracted_bytes == self.fixture_bytes

    @property
    def extracted_version(self) -> str:
        """``graph_version`` of the extracted IR."""
        return graph_version(self.extracted)

    @property
    def fixture_version(self) -> str:
        """``graph_version`` of the fixture's IR block."""
        return graph_version(self.fixture)

    def report(self) -> str:
        """A human-readable account of what differs — display only.

        Empty string when the two canonical forms agree.
        """
        if self.matched:
            return ""
        differences = diff_documents(
            json.loads(self.fixture_bytes), json.loads(self.extracted_bytes)
        )
        lines = [
            f"round-trip drift on {self.pair.name}",
            f"  fixture   {self.pair.fixture_path} ({self.pair.ir_key})",
            f"  builder   {self.pair.script}",
            f"  fixture   graph_version {self.fixture_version}",
            f"  extracted graph_version {self.extracted_version}",
        ]
        lines.extend(f"  - {difference}" for difference in differences)
        if not differences:  # pragma: no cover - bytes differ but JSON does not
            lines.append("  - canonical bytes differ with no structural difference to name")
        return "\n".join(lines)


def round_trip(pair: DriftPair) -> RoundTrip:
    """Build ``pair``'s graph, extract it, and canonicalize both sides.

    The builder is called here and nowhere else, so a pair's graph is constructed once per
    round trip and never module-level: importing :mod:`tests.drift.builders` defines
    factories only.
    """
    envelope = extract(pair.build())
    fixture_ir = pair.fixture_ir()
    return RoundTrip(
        pair=pair,
        extracted=envelope.ir,
        fixture=fixture_ir,
        extracted_bytes=canonical_bytes(envelope.ir),
        fixture_bytes=canonical_bytes(fixture_ir),
        warnings=envelope.warnings,
    )


def diff_documents(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Every place two canonical JSON documents differ, as one line each.

    ``expected`` is the fixture side and ``actual`` the extracted side, so a line reads in the
    direction a corpus author would ask about. Recursion is over the canonical form, whose
    arrays are already sorted (§6.2), so a positional comparison of two lists compares
    like with like.
    """
    where = path or "<document>"
    if type(expected) is not type(actual) and not _both_numbers(expected, actual):
        return [f"{where}: fixture has {_render(expected)}, extraction has {_render(actual)}"]
    if isinstance(expected, dict):
        return _diff_objects(expected, actual, path)
    if isinstance(expected, list):
        return _diff_arrays(expected, actual, path)
    if expected == actual:
        return []
    return [f"{where}: fixture has {_render(expected)}, extraction has {_render(actual)}"]


def _diff_objects(expected: dict[str, Any], actual: dict[str, Any], path: str) -> list[str]:
    """Key-by-key, in the union's sorted order so the report is stable."""
    lines: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        child = f"{path}.{key}" if path else key
        if key not in actual:
            lines.append(f"{child}: only the fixture has it ({_render(expected[key])})")
        elif key not in expected:
            lines.append(f"{child}: only extraction has it ({_render(actual[key])})")
        else:
            lines.extend(diff_documents(expected[key], actual[key], child))
    return lines


def _diff_arrays(expected: list[Any], actual: list[Any], path: str) -> list[str]:
    """Element by element, with the tail of the longer side named rather than truncated."""
    lines: list[str] = []
    for index in range(min(len(expected), len(actual))):
        lines.extend(diff_documents(expected[index], actual[index], f"{path}[{index}]"))
    for index in range(len(actual), len(expected)):
        lines.append(f"{path}[{index}]: only the fixture has it ({_render(expected[index])})")
    for index in range(len(expected), len(actual)):
        lines.append(f"{path}[{index}]: only extraction has it ({_render(actual[index])})")
    return lines


def _both_numbers(left: Any, right: Any) -> bool:
    """``1`` and ``1.0`` are the same JSON number; ``True`` is not one (``bool`` is an ``int``)."""
    return all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in (left, right)
    )


def _render(value: Any) -> str:
    """A value as compact JSON — the documents are JSON, so nothing here calls ``repr``."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
