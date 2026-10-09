"""Vedic references: they reproduce the published Positional Astronomy Centre longitudes, apply
the classical definitions consistently, and the boundary cases sit where a wrong frame flips."""

from __future__ import annotations

import json
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import PULL_FILE, REFERENCES_FILE, load_module
from benchmark.paths import DOMAINS_DIR
from benchmark.stats import angular_distance

FOLDER = DOMAINS_DIR / "vedic"
PAC_AGREEMENT_ARCSEC = 0.5
"""How closely the recomputation reproduces the agency tables, Moon included."""


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    """The pull module itself, for its definitions; nothing here contacts a source."""
    return load_module(FOLDER, PULL_FILE)


@pytest.fixture(scope="module")
def references() -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FOLDER / REFERENCES_FILE).read_text(encoding="utf-8"))
    return document


def test_recomputation_reproduces_the_agency_sidereal_longitudes(
    references: dict[str, Any],
) -> None:
    cases = {c["id"]: c for c in references["cases"]}
    assert len(references["cross_checks"]) == 3
    for cross in references["cross_checks"]:
        case = cases[cross["id"]]
        assert case["input"] == cross["input"]
        for graha, published in cross["expected"].items():
            off = angular_distance(case["expected"][graha], published) * 3600
            assert off < PAC_AGREEMENT_ARCSEC, (cross["id"], graha, off)


def test_derived_values_follow_from_each_longitude(
    pull: ModuleType, references: dict[str, Any]
) -> None:
    for case in references["cases"]:
        expected = case["expected"]
        for point in (*pull.GRAHA_CODES, "Lagna"):
            if point not in expected:
                continue
            longitude = expected[point]
            assert expected[f"{point} nakshatra"] == pull.nakshatra(longitude)
            assert expected[f"{point} pada"] == pull.pada(longitude)
            assert expected[f"{point} navamsa"] == pull.navamsa(longitude)
        assert expected["dasha lord"] == pull.dasha_lord(expected["Moon"])


def test_lagna_is_present_except_beyond_the_polar_circle_or_off_the_minute(
    pull: ModuleType, references: dict[str, Any]
) -> None:
    without = {c["id"] for c in references["cases"] if "Lagna" not in c["expected"]}
    assert without == {
        "tromso_midnight_sun",
        *(f"pac-{d}" for d in pull.PAC_DATES),
    }


def test_navamsa_sign_rule_is_the_ninth_part_count(pull: ModuleType) -> None:
    """Movable from itself, fixed from the 9th, dual from the 5th equals a plain count of ninths."""
    for index in range(108):
        midpoint = (index + 0.5) * pull.PADA_SPAN
        assert pull.navamsa(midpoint) == pull.SIGNS[index % 12]


def test_dasha_lords_and_years_follow_the_text(pull: ModuleType) -> None:
    span = pull.NAKSHATRA_SPAN
    assert pull.dasha_lord(0.5 * span) == "Ketu"  # Ashwini
    assert pull.dasha_lord(2.5 * span) == "Sun"  # Krittika
    assert pull.dasha_lord(26.5 * span) == "Mercury"  # Revati
    assert sum(pull.DASHA_YEARS.values()) == 120
    assert pull.dasha_balance_days(0.0) == pytest.approx(7 * pull.JULIAN_YEAR_DAYS)


def test_boundary_cases_change_under_a_frame_without_nutation(
    pull: ModuleType, references: dict[str, Any]
) -> None:
    """Each boundary graha sits just past a pada edge, so 18 arcseconds back changes the answer."""
    cases = {c["id"]: c["expected"] for c in references["cases"]}
    for case_id, (graha, _) in pull.BOUNDARY_CASES.items():
        longitude = cases[case_id][graha]
        past_edge = longitude % pull.PADA_SPAN * 3600
        assert 0 < past_edge < pull.BOUNDARY_MARGIN_ARCSEC, case_id
        shifted = longitude - 18 / 3600
        assert pull.pada(shifted) != cases[case_id][f"{graha} pada"]
        assert pull.navamsa(shifted) != cases[case_id][f"{graha} navamsa"]
    moon = cases["moon-nakshatra-edge"]["Moon"]
    assert pull.dasha_lord(moon - 18 / 3600) != cases["moon-nakshatra-edge"]["dasha lord"]
