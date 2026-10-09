"""The moon phase cases keep their distance from midnight Universal Time."""

from __future__ import annotations

import json

import pytest

from benchmark.domains import PULL_FILE, load_module
from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "moon-phases"


@pytest.mark.parametrize(
    ("time", "minutes"),
    [("00:33", 33), ("23:32", 28), ("12:00", 720), ("00:00", 0)],
)
def test_distance_from_midnight_wraps_across_the_day_boundary(time: str, minutes: int) -> None:
    helper = load_module(FOLDER, PULL_FILE).minutes_from_midnight
    assert helper(time) == minutes


def test_cases_cover_both_sides_of_midnight_and_every_phase() -> None:
    cases = json.loads((FOLDER / "references.json").read_text(encoding="utf-8"))["cases"]
    phases = {c["input"]["phase"] for c in cases}
    assert phases == {"New Moon", "First Quarter Moon", "Full Moon", "Third Quarter Moon"}
    assert {"new-2023-12-12", "full-2023-12-27"} <= {c["id"] for c in cases}
