"""The Mesoamerican calendar recomputation reproduces the published converter, value for value."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from benchmark.domains import load_pull
from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "mesoamerican-calendar"
GREGORIAN_ORDINAL_TO_JDN = 1_721_425
"""Julian Day Number minus the proleptic Gregorian ordinal, where 0001-01-01 is ordinal 1."""


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return load_pull(FOLDER)()


def test_recomputation_reproduces_every_converter_value(document: dict[str, Any]) -> None:
    cases = {c["id"]: c["expected"] for c in document["cases"]}
    assert document["cross_checks"]
    for cross in document["cross_checks"]:
        recomputed = cases[cross["id"]]
        for quantity, value in cross["expected"].items():
            assert recomputed[quantity] == value, (cross["id"], quantity)


def test_julian_day_number_matches_the_standard_library_calendar(document: dict[str, Any]) -> None:
    for case in document["cases"]:
        ordinal = date.fromisoformat(case["input"]["date"]).toordinal()
        assert case["expected"]["julian_day_number"] == ordinal + GREGORIAN_ORDINAL_TO_JDN


def test_cases_cover_wayeb_and_a_date_before_the_reform(document: dict[str, Any]) -> None:
    expected = {c["id"]: c["expected"] for c in document["cases"]}
    assert expected["wayeb-day"]["haab_month"] == "wayeb"
    assert date.fromisoformat(
        next(c["input"]["date"] for c in document["cases"] if c["id"] == "pre-reform")
    ) < date(1582, 10, 15)
