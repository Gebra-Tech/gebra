"""Golden-file plumbing for the rendering suite.

Goldens are committed text: the test renders a catalog case and compares byte-for-byte, which
is what makes "every variant renders" a claim about *what* was rendered rather than only that
nothing raised. One value is normalized — ``tool.version``, the only value REPORT-FORMAT-SPEC
§1.3 admits legitimately differs between two runs over identical input, and the only one
CLI-07's own goldens normalize (§7). The catalog's extracted subjects carry that same value as
their ``extractor_version`` (``variants.case_report``: the build that extracted them, as the
CLI and the snapshot engine record it), so the placeholder stands at both spots in a golden.

Regeneration is deliberate, not automatic::

    GEBRA_REGENERATE_GOLDENS=1 .venv/bin/python -m pytest tests/report -q

A regenerated golden lands with the change that justified it, and a diff nobody can explain is
drift by definition (WA-05's discipline, applied to this suite's own goldens).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

import gebra

__all__ = ["GOLDEN_ROOT", "REGENERATING", "compare_golden", "normalize"]

GOLDEN_ROOT: Final = Path(__file__).parent / "goldens"

#: The placeholder a golden carries where the installed build's version stood.
_VERSION_PLACEHOLDER: Final = "<gebra-version>"

#: The installed version as a whole token — never the tail of a V.S.F.E label or the head of
#: a longer version string. A bare substring replacement was enough while the version was
#: `0.0.1.dev0`; at `0.0.1` (GOV-14) it also matched inside the label `1.0.0.1` that a CLI
#: integration transcript prints, and would match inside `0.0.1.dev0` if such a literal ever
#: appears beside the tool version.
_VERSION_TOKEN: Final = re.compile(rf"(?<![\w.]){re.escape(gebra.__version__)}(?![\w.])")

REGENERATING: Final = os.environ.get("GEBRA_REGENERATE_GOLDENS") == "1"


def normalize(text: str) -> str:
    """Replace the installed ``tool.version`` with a placeholder (§1.3, §7)."""
    return _VERSION_TOKEN.sub(_VERSION_PLACEHOLDER, text)


def compare_golden(relative_path: str, rendered: str) -> None:
    """Assert ``rendered`` matches the committed golden, normalizing ``tool.version``.

    Raises:
        AssertionError: if the golden is missing or differs, unless ``GEBRA_REGENERATE_GOLDENS``
            asked for a regeneration pass, in which case the file is written.
    """
    path = GOLDEN_ROOT / relative_path
    normalized = normalize(rendered)
    if REGENERATING:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalized, encoding="utf-8")
        return
    assert path.is_file(), (
        f"{path} is missing; regenerate with GEBRA_REGENERATE_GOLDENS=1 and land the file "
        "with the change that justified it"
    )
    expected = path.read_text(encoding="utf-8")
    assert normalized == expected, f"{path} no longer matches the rendering"
