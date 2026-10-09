"""The Kabbalah recomputations reproduce the published worked examples and converter dates."""

from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import PULL_FILE, load_module
from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "kabbalah"


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    return load_module(FOLDER, PULL_FILE)


@pytest.fixture(scope="module")
def document(pull: ModuleType) -> dict[str, Any]:
    return pull.pull()  # type: ignore[no-any-return]


def test_recomputation_reproduces_every_worked_example_and_converter_date(
    pull: ModuleType, document: dict[str, Any]
) -> None:
    assert len(document["cross_checks"]) >= 15
    for cross in document["cross_checks"]:
        given = cross["input"]
        if "textHebrew" in given:
            recomputed = {"mispar_hechrachi": pull.mispar_hechrachi(given["textHebrew"])}
        else:
            recomputed = pull.hebrew_date(given["date"], given["afterSunset"])
        for quantity, value in cross["expected"].items():
            assert recomputed[quantity] == value, cross["id"]


def test_final_letters_count_as_regular_letters_except_in_mispar_gadol(pull: ModuleType) -> None:
    assert pull.mispar_hechrachi("ךםןףץ") == 20 + 40 + 50 + 80 + 90
    assert pull.mispar_gadol("ךםןףץ") == 500 + 600 + 700 + 800 + 900
    assert pull.mispar_hechrachi("שלום") == 376
    assert pull.mispar_gadol("שלום") == 936


def test_vowel_points_carry_no_value(pull: ModuleType) -> None:
    assert pull.mispar_hechrachi("אֶמֶת") == pull.mispar_hechrachi("אמת") == 441


def test_year_structure_matches_the_calendar_rules(pull: ModuleType) -> None:
    leap = [y for y in range(5760, 5779) if pull.leap_year(y)]
    assert len(leap) == 7
    assert {pull.days_in_year(y) for y in range(5700, 5800)} <= {353, 354, 355, 383, 384, 385}
    assert pull.hebrew_from_fixed(pull.fixed_from_hebrew(5784, 13, 1)) == (5784, 13, 1)


def test_every_day_round_trips_through_the_hebrew_calendar(pull: ModuleType) -> None:
    start = pull.new_year(5780)
    for rata_die in range(start, pull.new_year(5790)):
        year, month, day = pull.hebrew_from_fixed(rata_die)
        assert pull.fixed_from_hebrew(year, month, day) == rata_die


def test_cases_cover_the_edges_that_catch_a_wrong_convention(document: dict[str, Any]) -> None:
    cases = {c["id"]: c["expected"] for c in document["cases"]}
    assert cases["adar-i-end"]["month_number"] == 12 and cases["adar-i-end"]["day"] == 30
    assert cases["adar-ii-start"]["month_number"] == 13
    assert (
        cases["rosh-hashanah-5786"]["day"] == 1 and cases["rosh-hashanah-5786"]["month_number"] == 7
    )
    assert cases["after-sunset-eve"] == cases["rosh-hashanah-5786"]
    assert cases["eve-of-rosh-hashanah"]["hebrew_year"] == 5785
