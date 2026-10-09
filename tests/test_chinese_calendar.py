"""The sexagenary rules reproduce every transcribed table value, and the cases are well formed."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from typing import Any

import pytest

from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "chinese-calendar"
_spec = importlib.util.spec_from_file_location("chinese_calendar_pull", FOLDER / "pull.py")
assert _spec is not None and _spec.loader is not None
pull = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pull)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FOLDER / "references.json").read_text(encoding="utf-8"))
    return doc


def recompute(given: dict[str, Any]) -> dict[str, str]:
    stems: tuple[str, ...] = pull.STEMS
    if "date" in given:
        return {"day_pillar": pull.day_pillar(date.fromisoformat(given["date"]))}
    if "solar_year" in given:
        return {"year_pillar": pull.year_pillar(given["solar_year"])}
    if "year_stem" in given:
        stem = stems.index(given["year_stem"])
        return {"month_pillar": pull.month_pillar(stem, given["month_index"])}
    stem = stems.index(given["day_stem"])
    return {"hour_pillar": pull.hour_pillar(stem, given["hour"])}


def test_rules_reproduce_every_transcribed_value(document: dict[str, Any]) -> None:
    assert document["cross_checks"]
    for cross in document["cross_checks"]:
        assert recompute(cross["input"]) == cross["expected"], cross["id"]


def test_each_solar_year_lists_24_distinct_terms_in_order(document: dict[str, Any]) -> None:
    for case in document["cases"]:
        if case["id"].startswith("solar-terms-"):
            days = list(case["expected"].values())
            assert len(days) == 24 == len(set(days))
            assert days == sorted(days)


def test_boundary_cases_split_the_year_and_month_at_the_terms(document: dict[str, Any]) -> None:
    expected = {c["id"]: c["expected"] for c in document["cases"]}
    before, after = expected["pillars-before-lichun"], expected["pillars-after-lichun"]
    assert before["year_pillar"] != after["year_pillar"]
    assert before["month_pillar"].endswith("chou") and after["month_pillar"].endswith("yin")
