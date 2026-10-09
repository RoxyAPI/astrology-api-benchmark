from __future__ import annotations

from typing import Any

import pytest

from benchmark import ApiError, Case, Status, Unit, measure, measure_cases
from benchmark.schema import Chart, Measurement, References, parse_references
from benchmark.stats import angular_distance, deviation, mean, median, p95, summarize


@pytest.mark.parametrize(
    ("a", "b", "want"),
    [
        (10.0, 10.0, 0.0),
        (359.9, 0.1, 0.2),
        (0.1, 359.9, 0.2),
        (0.0, 180.0, 180.0),
        (90.0, 270.5, 179.5),
        (720.25, 0.0, 0.25),
        (-10.0, 350.0, 0.0),
    ],
)
def test_angular_distance_wraps(a: float, b: float, want: float) -> None:
    assert angular_distance(a, b) == pytest.approx(want, abs=1e-9)


def test_central_figures() -> None:
    values = [4.0, 1.0, 3.0, 2.0]
    assert median(values) == 2.5
    assert mean(values) == 2.5
    assert median([5.0]) == 5.0


def test_p95_is_nearest_rank() -> None:
    assert p95([float(v) for v in range(1, 21)]) == 19.0
    assert p95([float(v) for v in range(1, 101)]) == 95.0
    assert p95([float(v) for v in range(1, 211)]) == 200.0
    assert p95([7.0]) == 7.0


@pytest.mark.parametrize(
    ("unit", "expected", "actual", "want"),
    [
        (Unit.ARCSEC, 359.9999, 0.0001, 0.72),
        (Unit.ARCSEC, 132.5479089, 132.5479205, 0.04176),
        (Unit.SECONDS, "2000-01-01T12:00:00Z", "2000-01-01T13:00:30+01:00", 30.0),
        (Unit.DAYS, 1872000, 1871999, 1.0),
        (Unit.DAYS, "2012-12-21", "2012-12-23", 2.0),
        (Unit.EXACT, "ajaw", "ajaw", 0.0),
        (Unit.EXACT, "ajaw", "Ajaw", 1.0),
        (Unit.EXACT, 1, True, 1.0),
        (Unit.EXACT, 4, 4, 0.0),
    ],
)
def test_deviation_per_unit(unit: Unit, expected: Any, actual: Any, want: float) -> None:
    assert deviation(unit, expected, actual) == pytest.approx(want, abs=1e-4)


@pytest.mark.parametrize(
    ("unit", "expected", "actual"),
    [
        (Unit.ARCSEC, 1.0, "1.0"),
        (Unit.ARCSEC, 1.0, True),
        (Unit.SECONDS, "2000-01-01T12:00:00Z", "2000-01-01T12:00:00"),
        (Unit.DAYS, "2012-12-21", 5),
    ],
)
def test_unreadable_actual_is_missing(
    unit: Unit, expected: Any, actual: Any, charts: dict[str, Chart]
) -> None:
    refs = _refs(unit, expected, charts)
    m = measure(refs, refs.cases[0], "q", actual)
    assert m.status is Status.MISSING
    assert m.deviation is None
    assert m.note


def test_measure_pass_at_the_band_and_fail_beyond(charts: dict[str, Chart]) -> None:
    refs = _refs(Unit.DAYS, 10, charts, band=1)
    case = refs.cases[0]
    assert measure(refs, case, "q", 11).status is Status.PASS
    assert measure(refs, case, "q", 12).status is Status.FAIL
    assert measure(refs, case, "q", None).status is Status.MISSING


def test_measure_cases_records_errors_as_missing(charts: dict[str, Chart]) -> None:
    refs = _refs(Unit.EXACT, "a", charts, cases=3)

    def fetch(case: Case) -> dict[str, Any]:
        if case.id == "c0":
            return {"q": "a"}
        if case.id == "c1":
            raise ApiError("POST /x: HTTP 503")
        raise KeyError("planets")

    got = {m.case: m for m in measure_cases(refs, fetch)}
    assert got["c0"].status is Status.PASS
    assert got["c1"].status is Status.MISSING
    assert "503" in got["c1"].note
    assert got["c2"].status is Status.MISSING
    assert got["c2"].note.startswith("unexpected response: KeyError")


def test_absent_quantity_is_missing(charts: dict[str, Chart]) -> None:
    refs = _refs(Unit.EXACT, "a", charts)
    (m,) = measure_cases(refs, lambda case: {})
    assert m.status is Status.MISSING
    assert m.note == "absent from the response"


def test_summary_per_unit_with_worst_case_and_per_quantity_max() -> None:
    def m(case: str, quantity: str, unit: Unit, dev: float | None, status: Status) -> Measurement:
        return Measurement(case, quantity, unit, 0.0, None, dev, 36.0, status)

    rows = [
        m("a", "Sun", Unit.ARCSEC, 0.1, Status.PASS),
        m("b", "Sun", Unit.ARCSEC, 0.3, Status.PASS),
        m("a", "Moon", Unit.ARCSEC, 0.2, Status.PASS),
        m("b", "Moon", Unit.ARCSEC, 40.0, Status.FAIL),
        m("c", "Moon", Unit.ARCSEC, None, Status.MISSING),
        m("a", "sign", Unit.EXACT, 0.0, Status.PASS),
    ]
    arcsec, exact = summarize("d", rows)
    assert (arcsec.unit, exact.unit) == (Unit.ARCSEC, Unit.EXACT)
    assert (arcsec.points, arcsec.passed, arcsec.failed, arcsec.missing) == (5, 3, 1, 1)
    assert arcsec.median == pytest.approx(0.25)
    assert arcsec.mean == pytest.approx(10.15)
    assert arcsec.max == 40.0
    assert arcsec.p95 == 40.0
    assert arcsec.worst_case is not None
    assert (arcsec.worst_case.case, arcsec.worst_case.quantity) == ("b", "Moon")
    assert [(w.quantity, w.case, w.deviation) for w in arcsec.per_quantity_max] == [
        ("Moon", "b", 40.0),
        ("Sun", "b", 0.3),
    ]
    assert exact.points == 1
    assert [(t.limit, t.points) for t in arcsec.tiers] == [(10.0, 3), (1.0, 3), (0.1, 1)]
    assert exact.tiers == ()


def test_summary_with_nothing_measured() -> None:
    (s,) = summarize("d", [Measurement("a", "q", Unit.DAYS, 1, None, None, 0.0, Status.MISSING)])
    assert (s.median, s.p95, s.max, s.worst_case, s.per_quantity_max) == (
        None,
        None,
        None,
        None,
        (),
    )


def _refs(
    unit: Unit, expected: Any, charts: dict[str, Chart], *, band: float = 0, cases: int = 1
) -> References:
    doc = {
        "format": 1,
        "domain": "t",
        "sources": [
            {
                "name": "S",
                "citation": "A printed table",
                "retrieved": "2026-01-01",
                "licence": "Facts",
                "method": "Read",
            }
        ],
        "tolerances": [{"applies_to": "*", "value": band, "unit": unit.value, "why": "w"}],
        "cases": [
            {"id": f"c{i}", "input": {"i": i}, "expected": {"q": expected}} for i in range(cases)
        ],
    }
    return parse_references(doc, "t", charts)
