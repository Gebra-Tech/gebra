"""Golden plumbing for the CLI suite — the report suite's discipline, at this suite's root.

``normalize`` is imported from :mod:`tests.report.goldens` rather than restated: one field
is normalized (``tool.version``, per REPORT-FORMAT-SPEC §1.3 and CLI-SPEC §7's "goldens
normalize ``tool.version`` and nothing else"), and one implementation of that rule is how
the two suites stay the same rule. Regeneration is the same deliberate act::

    GEBRA_REGENERATE_GOLDENS=1 .venv/bin/python -m pytest tests/cli -q
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.report.goldens import REGENERATING, normalize

__all__ = ["GOLDEN_ROOT", "compare_golden"]

GOLDEN_ROOT: Final = Path(__file__).parent / "goldens"


def compare_golden(relative_path: str, captured: str) -> None:
    """Assert ``captured`` matches the committed golden, normalizing ``tool.version``.

    Raises:
        AssertionError: if the golden is missing or differs, unless
            ``GEBRA_REGENERATE_GOLDENS`` asked for a regeneration pass.
    """
    path = GOLDEN_ROOT / relative_path
    normalized = normalize(captured)
    if REGENERATING:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalized, encoding="utf-8")
        return
    assert path.is_file(), (
        f"{path} is missing; regenerate with GEBRA_REGENERATE_GOLDENS=1 and land the file "
        "with the change that justified it"
    )
    expected = path.read_text(encoding="utf-8")
    assert normalized == expected, f"{path} no longer matches the captured output"
