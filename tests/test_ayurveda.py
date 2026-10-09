"""Ayurveda references: the recomputation reproduces the published solstices and the published
sidereal Sun, and the season, edge-day and day-clock definitions behave."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import REFERENCES_FILE, load_pull
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import parse_instant

FOLDER = DOMAINS_DIR / "ayurveda"
USNO_AGREEMENT_SECONDS = 60
"""USNO publishes whole minutes, so the recomputed second sits within one of them."""
PAC_AGREEMENT_SECONDS = 30
"""The published longitudes are tabulated daily, so the crossing is a one day linear step, good
to about 5 seconds, plus the difference between delta T and the TDB minus UT Horizons prints."""


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    """The pull module itself, for its definitions; nothing here contacts a source."""
    module = inspect.getmodule(load_pull(FOLDER))
    assert module is not None
    return module


@pytest.fixture(scope="module")
def references() -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FOLDER / REFERENCES_FILE).read_text(encoding="utf-8"))
    return document


def instant(value: str) -> datetime:
    when = parse_instant(value)
    assert when is not None, value
    return when


def seconds_between(a: str, b: str) -> float:
    return abs((instant(a) - instant(b)).total_seconds())


def test_recomputation_reproduces_the_published_cross_checks(references: dict[str, Any]) -> None:
    cases = {c["id"]: c for c in references["cases"]}
    by_source = {
        "US Naval Observatory seasons": USNO_AGREEMENT_SECONDS,
        "Positional Astronomy Centre, Kolkata": PAC_AGREEMENT_SECONDS,
    }
    assert len(references["cross_checks"]) == 4
    for cross in references["cross_checks"]:
        case = cases[cross["id"]]
        assert case["input"] == cross["input"]
        for quantity, published in cross["expected"].items():
            off = seconds_between(case["expected"][quantity], published)
            assert off < by_source[cross["source"]], (cross["id"], quantity, off)


def test_every_instant_is_in_the_past(references: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    for case in references["cases"]:
        for quantity, value in case["expected"].items():
            when = parse_instant(value) if isinstance(value, str) else None
            if when is not None:
                assert when < now, (case["id"], quantity)


def test_each_edge_has_a_case_before_and_after_it(references: dict[str, Any]) -> None:
    cases = {c["id"]: c["expected"] for c in references["cases"]}
    for name in ("hemanta-sisira", "sisira-vasanta", "vasanta-grisma", "grisma-varsa"):
        before, after = cases[f"{name}-before"], cases[f"{name}-after"]
        assert before["ritu end"] == after["ritu start"], name
        assert before["ritu"] != after["ritu"], name


def test_the_late_day_edge_reads_the_outgoing_season(references: dict[str, Any]) -> None:
    """The December edge falls after midday UT, so that date still names the outgoing season."""
    cases = {c["id"]: c for c in references["cases"]}
    before = cases["hemanta-sisira-before"]
    assert before["input"]["ritucharya"]["date"] == before["expected"]["ritu end"][:10]
    assert before["expected"]["ritu"] == "hemanta"


def test_both_zodiacs_and_the_south_disagree_on_the_same_date(references: dict[str, Any]) -> None:
    cases = {c["id"]: c["expected"] for c in references["cases"]}
    assert cases["divergence-tropical"]["ritu"] == "vasanta"
    assert cases["divergence-sidereal"]["sidereal ritu"] == "sisira"
    assert cases["southern-march"]["southern ritu"] == "sarad"


def test_season_follows_the_sun_longitude(pull: ModuleType) -> None:
    longitudes = (270, 329.9, 330, 29.9, 30, 89.9, 90, 149.9, 150, 209.9, 210, 269.9)
    assert [pull.ritu_index(d) for d in longitudes] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_edge_days_straddle_midday(pull: ModuleType) -> None:
    morning = datetime(2026, 2, 18, 9, tzinfo=UTC)
    evening = datetime(2026, 2, 18, 15, tzinfo=UTC)
    assert pull.edge_days(morning) == ("2026-02-17", "2026-02-18")
    assert pull.edge_days(evening) == ("2026-02-18", "2026-02-19")


def test_signed_offset_wraps_the_zero_edge(pull: ModuleType) -> None:
    assert pull.signed_offset(359.5, 0.0) == pytest.approx(-0.5)
    assert pull.signed_offset(0.5, 0.0) == pytest.approx(0.5)


def test_the_day_clock_cases_follow_the_thirds_and_the_fixed_window(
    references: dict[str, Any],
) -> None:
    checked = 0
    for case in references["cases"]:
        if "dinacharya" not in case["input"]:
            continue
        values = {k: instant(v) for k, v in case["expected"].items() if k != "dosha order"}
        assert case["expected"]["dosha order"] == "kapha pitta vata kapha pitta vata"
        day = (values["sunset"] - values["sunrise"]).total_seconds() / 3
        night = (values["next sunrise"] - values["sunset"]).total_seconds() / 3
        pairs = (
            ("day pitta start", "sunrise", day),
            ("day vata start", "day pitta start", day),
            ("night pitta start", "sunset", night),
            ("night vata start", "night pitta start", night),
            ("sunrise", "brahma muhurta start", 96 * 60),
            ("sunrise", "brahma muhurta end", 48 * 60),
        )
        for later, earlier, seconds in pairs:
            gap = (values[later] - values[earlier]).total_seconds()
            assert gap == pytest.approx(seconds, abs=0.002), (case["id"], later)
        checked += 1
    assert checked == len(pull_cases(references))


def pull_cases(references: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in references["cases"] if "dinacharya" in c["input"]]
