"""The biorhythm recomputation follows the sine definition and the calendar day count."""

from __future__ import annotations

from typing import Any

import pytest

from benchmark.domains import load_pull
from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "biorhythm"


@pytest.fixture(scope="module")
def cases() -> dict[str, dict[str, Any]]:
    return {c["id"]: c["expected"] for c in load_pull(FOLDER)()["cases"]}


def test_every_cycle_starts_at_zero_on_the_birth_date(cases: dict[str, dict[str, Any]]) -> None:
    expected = cases["birth-day"]
    assert expected["days_since_birth"] == 0
    for name in ("physical", "emotional", "intellectual"):
        assert expected[f"{name}_percent"] == 0
        assert expected[f"{name}_raw"] == "0.0000"


def test_all_cycles_return_to_zero_together_after_the_product_of_the_periods(
    cases: dict[str, dict[str, Any]],
) -> None:
    expected = cases["triple-return"]
    assert expected["days_since_birth"] == 21_252
    for name in ("physical", "emotional", "intellectual"):
        assert expected[f"{name}_percent"] == 0


def test_the_day_count_follows_the_calendar_across_leap_days(
    cases: dict[str, dict[str, Any]],
) -> None:
    assert cases["leap-day-span"]["days_since_birth"] == 24 * 365 + 6
    assert cases["across-leap-day"]["days_since_birth"] == 61
    assert cases["on-anniversary"]["days_since_birth"] == 36 * 365 + 9
