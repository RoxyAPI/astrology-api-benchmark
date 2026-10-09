"""Deviation per unit, the comparison that turns a value into a Measurement, and the summaries."""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from benchmark.api import ApiError
from benchmark.schema import (
    Case,
    Measurement,
    References,
    Status,
    Summary,
    Tier,
    Unit,
    Value,
    Worst,
    is_number,
    parse_day,
    parse_instant,
)

type Fetch = Callable[[Case], Mapping[str, Any]]
"""Calls the API for one case and returns the measured value per quantity name."""

TIER_LIMITS: Mapping[Unit, tuple[float, ...]] = {
    Unit.ARCSEC: (10.0, 1.0, 0.1),
    Unit.SECONDS: (60.0, 10.0, 1.0),
}
"""Precision tiers per unit, loosest first. They never decide a pass: the pass bands do."""

_RESPONSE_ERRORS = (KeyError, IndexError, TypeError, ValueError, AttributeError)


class UnmeasurableError(ValueError):
    """The API returned a value that cannot be compared with the reference."""


def angular_distance(a: float, b: float) -> float:
    """Smallest separation of two angles in degrees, so 359.9 and 0.1 are 0.2 apart."""
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def median(values: Sequence[float]) -> float:
    return statistics.median(values)


def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values)


def p95(values: Sequence[float]) -> float:
    """Nearest-rank 95th percentile: the smallest value at or above 95 percent of the points."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def deviation(unit: Unit, expected: Value, actual: object) -> float:
    """Distance between a reference and a measured value, in ``unit``."""
    match unit:
        case Unit.ARCSEC:
            if not is_number(actual):
                raise UnmeasurableError("not a number")
            return angular_distance(float(expected), float(actual)) * 3600.0
        case Unit.SECONDS:
            want = parse_instant(str(expected))
            got = parse_instant(actual) if isinstance(actual, str) else None
            if want is None or got is None:
                raise UnmeasurableError("not an ISO 8601 instant with an offset")
            return abs((got - want).total_seconds())
        case Unit.DAYS:
            if is_number(expected) and is_number(actual):
                return abs(float(actual) - float(expected))
            want_day = parse_day(expected) if isinstance(expected, str) else None
            got_day = parse_day(actual) if isinstance(actual, str) else None
            if want_day is None or got_day is None:
                raise UnmeasurableError("not the same kind of day value as the reference")
            return float(abs((got_day - want_day).days))
        case Unit.EXACT:
            same_kind = isinstance(actual, bool) == isinstance(expected, bool)
            return 0.0 if same_kind and actual == expected else 1.0


def measure(refs: References, case: Case, quantity: str, actual: object) -> Measurement:
    """Compare one returned value with the case reference under the quantity tolerance."""
    tolerance = refs.tolerance_for(quantity)
    expected = case.expected[quantity]
    if actual is None:
        return missing(refs, case, quantity, "null in the response")
    try:
        dev = deviation(tolerance.unit, expected, actual)
    except UnmeasurableError as e:
        return missing(refs, case, quantity, f"{e}: {actual!r}")
    return Measurement(
        case=case.id,
        quantity=quantity,
        unit=tolerance.unit,
        expected=expected,
        actual=actual if isinstance(actual, str | int | float | bool) else str(actual),
        deviation=dev,
        tolerance=tolerance.value,
        status=Status.PASS if dev <= tolerance.value else Status.FAIL,
    )


def missing(refs: References, case: Case, quantity: str, note: str) -> Measurement:
    tolerance = refs.tolerance_for(quantity)
    return Measurement(
        case=case.id,
        quantity=quantity,
        unit=tolerance.unit,
        expected=case.expected[quantity],
        actual=None,
        deviation=None,
        tolerance=tolerance.value,
        status=Status.MISSING,
        note=note,
    )


def measure_cases(refs: References, fetch: Fetch) -> list[Measurement]:
    """Run ``fetch`` per case and measure every expected quantity.

    A failed request or an unexpected response shape marks that case MISSING with the reason
    and the run continues, so one broken endpoint never hides the rest of the scorecard.
    """
    measurements: list[Measurement] = []
    for case in refs.cases:
        note = "absent from the response"
        try:
            actuals: Mapping[str, Any] = fetch(case)
        except ApiError as e:
            actuals, note = {}, str(e)
        except _RESPONSE_ERRORS as e:
            actuals, note = {}, f"unexpected response: {type(e).__name__} {e}"
        for quantity in case.expected:
            if quantity in actuals:
                measurements.append(measure(refs, case, quantity, actuals[quantity]))
            else:
                measurements.append(missing(refs, case, quantity, note))
    return measurements


def summarize(domain: str, measurements: Iterable[Measurement]) -> tuple[Summary, ...]:
    """One Summary per unit present, in ``Unit`` order."""
    by_unit: dict[Unit, list[Measurement]] = {}
    for m in measurements:
        by_unit.setdefault(m.unit, []).append(m)
    return tuple(_summary(domain, u, by_unit[u]) for u in Unit if u in by_unit)


def _summary(domain: str, unit: Unit, points: list[Measurement]) -> Summary:
    measured = [Worst(m.case, m.quantity, m.deviation) for m in points if m.deviation is not None]
    devs = [w.deviation for w in measured]
    per_quantity: dict[str, Worst] = {}
    for w in measured:
        best = per_quantity.get(w.quantity)
        if best is None or w.deviation > best.deviation:
            per_quantity[w.quantity] = w
    ranked = tuple(sorted(per_quantity.values(), key=lambda w: (-w.deviation, w.quantity)))
    return Summary(
        domain=domain,
        unit=unit,
        points=len(points),
        passed=sum(m.status is Status.PASS for m in points),
        failed=sum(m.status is Status.FAIL for m in points),
        missing=sum(m.status is Status.MISSING for m in points),
        median=median(devs) if devs else None,
        mean=mean(devs) if devs else None,
        p95=p95(devs) if devs else None,
        max=max(devs) if devs else None,
        worst_case=ranked[0] if ranked else None,
        per_quantity_max=ranked,
        tiers=tuple(
            Tier(limit, sum(d <= limit for d in devs)) for limit in TIER_LIMITS.get(unit, ())
        ),
    )
