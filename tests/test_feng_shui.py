"""The printed rules reproduce every transcribed table value, and the cases are well formed."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest

from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "feng-shui"
_spec = importlib.util.spec_from_file_location("feng_shui_pull", FOLDER / "pull.py")
assert _spec is not None and _spec.loader is not None
pull = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pull)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FOLDER / "references.json").read_text(encoding="utf-8"))
    return doc


def era_year(era: str, year_pillar: str) -> int:
    """Solar year of a pillar inside an era of the cycle that opened in 1864."""
    first = pull.CYCLE_START + 60 * pull.ERAS.index(era)
    return next(y for y in range(first, first + 60) if pull.pillar(y) == year_pillar)


def recompute(given: dict[str, Any]) -> list[dict[str, Any]]:
    if "gender" in given:
        assert era_year(given["era"], given["year_pillar"]) == given["solar_year"]
        return [{"kua": pull.kua(given["solar_year"], given["gender"])}]
    if "year_pillars" in given:
        years = [era_year(given["era"], p) for p in given["year_pillars"]]
        return [{"annual_center": pull.annual_star(y)} for y in years]
    if "facing" in given:
        chart = pull.natal_expected(given["period"], given["facing"])
        keys = ("mountain_center", "water_center", "mountain_flight", "water_flight")
        return [{k: chart[k] for k in keys}]
    plate = pull.fly(pull.annual_star(given["solar_year"]))
    return [{f"annual_{p.lower()}": s for p, s in plate.items()}]


def test_rules_reproduce_every_transcribed_value(document: dict[str, Any]) -> None:
    assert document["cross_checks"]
    for cross in document["cross_checks"]:
        for got in recompute(cross["input"]):
            assert got == cross["expected"], cross["id"]


def test_transcribed_tables_are_complete() -> None:
    assert all(len(d) == 60 for pair in pull.GUJIN_TABLE.values() for d in pair)
    pillars = [p for _, row in pull.XIEJI_YEAR_STARS for p in row.split()]
    assert sorted(pillars) == sorted(pull.pillar(y) for y in range(1864, 1924))
    assert len(pull.SHEN_TABLE) == 24 and all(len(r.split()) == 9 for r in pull.SHEN_TABLE.values())


def test_every_errata_row_breaks_the_rule() -> None:
    """The rows left out are exactly the ones the rule cannot reproduce as printed."""
    for mountain, row in pull.SHEN_TABLE.items():
        for period, code in enumerate(row.split(), start=1):
            chart = pull.natal(period, pull.sitting(mountain))
            flights = "".join(chart[f][0].upper() for f in ("mountain_flight", "water_flight"))
            agrees = code[2:] == flights
            assert agrees != ((mountain, period) in pull.SHEN_ERRATA), (mountain, period)


def test_every_plate_holds_each_star_once(document: dict[str, Any]) -> None:
    for case in document["cases"]:
        for plate in ("annual", "period", "mountain", "water"):
            stars = [v for k, v in case["expected"].items() if k.startswith(f"{plate}_")]
            stars = [s for s in stars if isinstance(s, int)]
            assert not stars or sorted(stars) == list(range(1, 10)), (case["id"], plate)


def test_boundary_cases_split_the_year_at_li_chun(document: dict[str, Any]) -> None:
    expected = {c["id"]: c["expected"] for c in document["cases"]}
    assert expected["kua-before-lichun-2026-male"]["solar_year"] == 2025
    assert expected["kua-lichun-day-2026-female"]["solar_year"] == 2025
    assert expected["kua-after-lichun-2026-male"]["solar_year"] == 2026
    assert expected["kua-early-lichun-2025-male"]["boundary_date"] == "2025-02-03"
    assert expected["kua-early-lichun-2025-male"]["solar_year"] == 2025
    for case_id, lodged in (("kua-after-lichun-2026-female", 8), ("kua-raw-five-1986-male", 2)):
        assert expected[case_id]["raw_kua"] == 5 and expected[case_id]["kua"] == lodged
