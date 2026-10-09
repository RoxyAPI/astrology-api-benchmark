"""Forecast references: the Horizons recomputation reproduces the published equinox and solstice,
and the root finders behave on known curves."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import REFERENCES_FILE, load_pull
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import parse_instant

FOLDER = DOMAINS_DIR / "forecast"
USNO_AGREEMENT_SECONDS = 60
"""USNO publishes whole minutes, so the recomputed second sits within one of them."""


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


def seconds_between(a: str, b: str) -> float:
    first, second = parse_instant(a), parse_instant(b)
    assert first is not None and second is not None
    return abs((first - second).total_seconds())


def test_recomputation_reproduces_the_published_equinox_and_solstice(
    references: dict[str, Any],
) -> None:
    cases = {c["id"]: c for c in references["cases"]}
    assert len(references["cross_checks"]) == 2
    for cross in references["cross_checks"]:
        case = cases[cross["id"]]
        assert case["input"] == cross["input"]
        for quantity, published in cross["expected"].items():
            off = seconds_between(case["expected"][quantity], published)
            assert off < USNO_AGREEMENT_SECONDS, (cross["id"], quantity, off)


def test_every_instant_is_in_the_past_and_both_tables_agree(references: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    for case in references["cases"]:
        values = set(case["expected"].values())
        assert len(values) == 1, case["id"]
        (value,) = values
        when = parse_instant(value)
        assert when is not None and when < now, case["id"]


def test_ingress_boundary_follows_the_direction_of_motion(pull: ModuleType) -> None:
    enter_pisces = pull.boundary_entering("Pisces")
    assert enter_pisces(329.9, 330.1) == 330.0
    assert enter_pisces(360.1, 359.9) == 360.0
    assert enter_pisces(330.1, 330.3) is None
    assert pull.boundary_entering("Aries")(359.9, 360.1) == 360.0


def test_crossing_root_on_a_cubic(pull: ModuleType) -> None:
    origin = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [(origin + timedelta(hours=h), 10.0 + 0.5 * h + 0.01 * h**3) for h in range(4)]
    root = pull.bisect(lambda t: pull.lagrange(rows, t) - 10.8, rows[1][0], rows[2][0])
    hours = (root - origin).total_seconds() / 3600
    assert 10.0 + 0.5 * hours + 0.01 * hours**3 == pytest.approx(10.8, abs=1e-6)


def test_station_fit_recovers_a_known_vertex(pull: ModuleType) -> None:
    points = [(x / 50, 3.0 - 2.0 * (x / 50 - 0.123) ** 2) for x in range(-50, 51)]
    coefficients = pull.polyfit(points)
    slope = sum(k * c * 0.123 ** (k - 1) for k, c in enumerate(coefficients) if k)
    assert slope == pytest.approx(0.0, abs=1e-9)
