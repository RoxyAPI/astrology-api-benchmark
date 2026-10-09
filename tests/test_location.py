"""The location reference follows the pinned database, and the checker pins places and dates."""

from __future__ import annotations

import importlib.util
import zoneinfo
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import load, load_pull
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import Chart, Status
from tests.conftest import FakeApi

FOLDER = DOMAINS_DIR / "location"


def _module(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"location_{filename}", FOLDER / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return load_pull(FOLDER)()


def test_committed_references_equal_a_fresh_pull(
    document: dict[str, Any], charts: dict[str, Chart]
) -> None:
    committed = {c.id: dict(c.expected) for c in load(FOLDER, charts).references.cases}
    assert committed == {c["id"]: c["expected"] for c in document["cases"]}


def test_schedule_matches_the_database_at_every_row_edge(document: dict[str, Any]) -> None:
    check, pull = _module("check.py"), _module("pull.py")
    for case in document["cases"]:
        zone = pull.database_zone(case["expected"]["timezone"])
        rows = case["input"]["offsets"]
        for start, seconds in rows:
            instant = datetime.fromisoformat(start)
            assert check.offset_seconds(rows, instant) == seconds
            assert pull.offset_seconds(zone, instant) == seconds
            assert pull.offset_seconds(zone, instant - timedelta(seconds=1)) != seconds or (
                start == rows[0][0]
            )


@pytest.mark.parametrize(
    ("case_id", "when", "seconds"),
    [
        ("sydney", datetime(2026, 1, 15, tzinfo=UTC), 39600),
        ("sydney", datetime(2026, 7, 15, tzinfo=UTC), 36000),
        ("santiago", datetime(2026, 1, 15, tzinfo=UTC), -10800),
        ("santiago", datetime(2026, 7, 15, tzinfo=UTC), -14400),
        ("apia", datetime(2020, 2, 1, tzinfo=UTC), 50400),
        ("apia", datetime(2026, 2, 1, tzinfo=UTC), 46800),
        ("phoenix", datetime(2026, 7, 15, tzinfo=UTC), -25200),
        ("kathmandu", datetime(2026, 7, 15, tzinfo=UTC), 20700),
    ],
)
def test_offsets_at_dates_the_rules_decide(
    document: dict[str, Any], case_id: str, when: datetime, seconds: int
) -> None:
    case = next(c for c in document["cases"] if c["id"] == case_id)
    assert _module("check.py").offset_seconds(case["input"]["offsets"], when) == seconds


def test_zones_exist_in_the_pinned_database(document: dict[str, Any]) -> None:
    for case in document["cases"]:
        assert case["expected"]["timezone"] in zoneinfo.available_timezones()


def test_cases_include_ambiguous_names_in_different_zones(document: dict[str, Any]) -> None:
    springfields = {
        c["expected"]["timezone"] for c in document["cases"] if c["input"]["q"] == "Springfield"
    }
    assert len(springfields) == 2


def test_check_pins_the_place_and_reads_the_offset_at_the_run_instant(
    charts: dict[str, Chart],
) -> None:
    module = _module("check.py")
    refs = load(FOLDER, charts).references
    when = datetime(2026, 1, 15, 12, tzinfo=UTC)
    cities = [
        {
            "city": c.input["q"],
            "iso2": c.input["iso2"],
            "province": c.input["province"],
            "timezone": c.expected["timezone"],
            "utcOffset": module.offset_seconds(c.input["offsets"], when) / 3600,
        }
        for c in refs.cases
        if c.input
    ]

    def answer(method: str, path: str, body: Mapping[str, Any] | None) -> Any:
        return {"cities": cities}

    measurements = module.check(FakeApi(answer), refs, when)
    assert {m.status for m in measurements} == {Status.PASS}
    assert len(measurements) == 2 * len(refs.cases)
