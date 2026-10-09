"""Panchang references: the PAC tables give the same limbs, the boundary cases sit just past an
edge, and the definitions follow the text."""

from __future__ import annotations

import inspect
import json
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import REFERENCES_FILE, load_pull
from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "panchang"


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    module = inspect.getmodule(load_pull(FOLDER))
    assert module is not None
    return module


@pytest.fixture(scope="module")
def references() -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FOLDER / REFERENCES_FILE).read_text(encoding="utf-8"))
    return document


def test_published_longitudes_give_the_recomputed_limbs(
    pull: ModuleType, references: dict[str, Any]
) -> None:
    cases = {c["id"]: c for c in references["cases"]}
    assert len(references["cross_checks"]) == len(pull.PAC_DATES) == 3
    for cross in references["cross_checks"]:
        case = cases[cross["id"]]
        assert case["input"] == cross["input"]
        assert case["expected"] == cross["expected"]
        day = cross["id"].removeprefix("pac-")
        assert pull.published_limbs(pull.PAC_LONGITUDES[day]) == cross["expected"]


def test_karana_slots_follow_the_text(pull: ModuleType) -> None:
    """Burgess table: Kimstughna 1st, Bava 2nd, 9th, ..., Vishti 8th, 15th, ..., Shakuni 58th."""
    assert pull.karana(0) == pull.KIMSTUGHNA
    for half in (2, 9, 16, 23, 30, 37, 44, 51):
        assert pull.karana(half - 1) == 1
    for half in (8, 15, 22, 29, 36, 43, 50, 57):
        assert pull.karana(half - 1) == 7
    assert pull.karana(57) == pull.SHAKUNI
    assert pull.karana(58) is None
    assert pull.karana(59) is None


def test_unit_arithmetic(pull: ModuleType) -> None:
    assert pull.tithi(0.0) == 1
    assert pull.tithi(179.99) == 15
    assert pull.tithi(359.99) == 30
    assert pull.yoga(0.0) == 1
    assert pull.yoga(359.99) == 27
    assert pull.elongation(350.0, 10.0) == pytest.approx(20.0)


def test_vara_is_the_weekday_of_the_sunrise_date(pull: ModuleType) -> None:
    assert pull.vara("2026-03-08") == "Sunday"
    assert pull.vara("2026-03-09") == "Monday"


def test_boundary_cases_flip_under_a_small_error(
    pull: ModuleType, references: dict[str, Any]
) -> None:
    """Each sits just past an edge of its limb, so a small angular error changes the answer."""
    expected = {c["id"]: c["expected"] for c in references["cases"]}
    assert {case[0] for case in pull.BOUNDARY_CASES} <= set(expected)
    kinds = {case[1] for case in pull.BOUNDARY_CASES}
    assert kinds == {"tithi", "karana", "yoga"}
    # An ayanamsa 17.5 arcseconds higher moves the yoga sum back by 35 arcseconds, past the
    # margin the yoga case sits inside.
    assert pull.YOGA_MARGIN_ARCSEC < 2 * 17.5


def test_sunrise_values_carry_the_case_offset(references: dict[str, Any]) -> None:
    for case in references["cases"]:
        if "sunrise" not in case["expected"]:
            continue
        sunrise = case["expected"]["sunrise"]
        assert sunrise.startswith(case["input"]["date"])
        assert sunrise.endswith(
            ("+00:00", "+05:30", "-05:00", "+11:00", "-10:00", "+02:00", "+09:00")
        )
