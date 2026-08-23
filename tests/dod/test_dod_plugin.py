"""The pytest-plugin legs of the DoD: the healthy agent's wedge five, and R2's flag.

C1 opens with "the travel-booking tutorial agent verifies end-to-end through the pytest
plugin; its healthy v1 passes the wedge five clean" — the marked test below *is* that run,
five items in this very session, one per wedge property over the live agent. The R2 catch
is then demonstrated with the literal flag the ruling names: an inner pytest session over
the defect-3 variant under ``--gebra-strict=determinism-replay`` goes red on exactly the
``determinism-replay`` item, and the same session without the flag is green — the
API-level twin of both facts lives in ``test_dod_defects.py``; this file is where the
flag itself is observed doing it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.sample_workflows import travel_booking as tb

pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.gebra(name="travel_agent")
def test_gebra() -> Any:
    """Healthy v1 through the plugin — five items, one per wedge property, all green."""
    return tb.build_travel_booking_agent()


_DEFECT3_SOURCE = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
import pytest

from tests.sample_workflows.travel_booking_defects import build_defect_3_false_determinism


@pytest.mark.gebra(name="defect3")
def test_gebra():
    return build_defect_3_false_determinism()
"""


def test_the_defect_3_catch_under_the_literal_flag(pytester: pytest.Pytester) -> None:
    """R2's own spelling: ``--gebra-strict=determinism-replay`` gates the variant red.

    Exactly the promoted item fails — four wedge items stay green — so the catch is the
    seeded defect's, not a policy-wide red.
    """
    pytester.makepyfile(test_defect3=_DEFECT3_SOURCE)
    result = pytester.runpytest("-v", "--gebra-strict=determinism-replay")
    result.assert_outcomes(passed=4, failed=1, errors=0, skipped=0)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*test_gebra[[]defect3-determinism-replay[]]*FAILED*"])


def test_without_the_flag_the_same_session_is_green(pytester: pytest.Pytester) -> None:
    """The control: default policy leaves the WARNING finding a note, and the session
    passes — which is why R2 rules the promotion into the DoD catch at all."""
    pytester.makepyfile(test_defect3=_DEFECT3_SOURCE)
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=5, failed=0, errors=0, skipped=0)
    assert result.ret == pytest.ExitCode.OK
