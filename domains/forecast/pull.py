"""Rebuild ``references.json``: sign ingress, station and exact transit instants from Horizons.

Every instant is a root of the apparent geocentric ecliptic longitude of date that NASA JPL
Horizons prints (OBSERVER table, QUANTITIES 31, seven decimal degrees, times in UT), found here in
two passes:

- A daily table over the calendar month the event is declared in brackets it: the longitude
  crosses a sign boundary (ingress) or the natal point plus the aspect angle (exact transit)
  between two rows, or the daily motion changes sign (station). The bracket must be the only one
  of its kind in the month, so the event a case names is never ambiguous.
- A finer table around the bracket locates it. A crossing is the root of the cubic through the
  four hourly rows around it (Lagrange interpolation, Meeus, Astronomical Algorithms, 2nd edition,
  chapter 3, equation 3.8 form), found by bisection to a millisecond; over one hour the cubic
  departs from the tabulated motion by far less than the last printed digit. A station is the
  zero of the rate, which no table prints: the longitude tabulated every ten minutes over two days
  either side is fitted by least squares with a polynomial of degree six in time, and the root of
  its derivative is found by bisection. A station is the vertex of a near parabola, so its instant
  rests on the curvature of days of motion rather than on one row; changing the degree or the span
  moves it by under a second.

Times are UT as Horizons prints them. Every event is in the past: Horizons holds delta T flat for
future dates, so a future instant would inherit an extrapolation rather than an observation.

The Sun reaching longitude 0 and 90 degrees is also the March equinox and the June solstice, which
the US Naval Observatory publishes to the minute; those two values are transcribed under
``cross_checks`` and a test holds the recomputation to them.

Run it with ``uv run python -m benchmark pull forecast``; nothing else in the repo contacts a
source.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from benchmark import horizons
from benchmark.fetch import get_text
from benchmark.schema import load_charts

USNO_SEASONS_URL = "https://aa.usno.navy.mil/api/seasons"
USNO_DOC_URL = "https://aa.usno.navy.mil/data/api"

# Sun to Mars by their own Horizons centres, Jupiter to Pluto by the system barycentres the
# planetary ephemeris integrates, as in the western-planets domain.
BODY_CODES: dict[str, str] = {
    "Sun": "10",
    "Moon": "301",
    "Mercury": "199",
    "Venus": "299",
    "Mars": "499",
    "Jupiter": "5",
    "Saturn": "6",
    "Uranus": "7",
    "Neptune": "8",
    "Pluto": "9",
}
SIGNS = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
)  # fmt: skip
ASPECT_DEGREES = {"conjunction": 0.0, "sextile": 60.0, "square": 90.0, "trine": 120.0}
ASPECT_DEGREES["opposition"] = 180.0

NATAL_CHART = "obama"
"""Birth data for every forecast request. Only the exact transit depends on it."""
WINDOW_DAYS = 2
"""The forecast request spans the UT date of the event plus or minus this many days."""
STATION_HALF_SPAN = timedelta(days=2)
STATION_STEP = "10m"
STATION_DEGREE = 6
BISECTION_SECONDS = 0.001
HOURLY = timedelta(hours=1)
DAILY = timedelta(days=1)

INGRESS, STATION, TRANSIT = "ingress", "station", "transit"
MONTHLY_SUFFIX = ", monthly table"
"""Quantity name suffix for an ingress read from the monthly transit table."""


@dataclass(frozen=True, slots=True)
class Event:
    """One instant the API reports, declared by kind, body and the UT month it falls in."""

    id: str
    body: str
    kind: str
    month: str
    """``YYYY-MM``: the event must be the only one of its kind for the body in this month."""
    sign: str | None = None
    """Ingress: the sign entered, directly or retrograde."""
    station: str | None = None
    """Station: ``retrograde`` or ``direct``."""
    natal: str | None = None
    """Exact transit: the natal body aspected."""
    aspect: str | None = None
    forecast: bool = True
    """False for the Moon, which the forecast timeline leaves out; its ingress comes only from
    the monthly table."""


EVENTS: tuple[Event, ...] = (
    Event("sun-enters-aries-2025-03", "Sun", INGRESS, "2025-03", sign="Aries"),
    Event("sun-enters-cancer-2025-06", "Sun", INGRESS, "2025-06", sign="Cancer"),
    Event("mercury-enters-aries-2025-03", "Mercury", INGRESS, "2025-03", sign="Aries"),
    Event("mercury-reenters-pisces-2025-03", "Mercury", INGRESS, "2025-03", sign="Pisces"),
    Event("venus-reenters-pisces-2025-03", "Venus", INGRESS, "2025-03", sign="Pisces"),
    Event("mars-enters-leo-2025-04", "Mars", INGRESS, "2025-04", sign="Leo"),
    Event("jupiter-enters-cancer-2025-06", "Jupiter", INGRESS, "2025-06", sign="Cancer"),
    Event("uranus-enters-gemini-2025-07", "Uranus", INGRESS, "2025-07", sign="Gemini"),
    Event("neptune-enters-aries-2025-03", "Neptune", INGRESS, "2025-03", sign="Aries"),
    Event("moon-enters-virgo-2025-03", "Moon", INGRESS, "2025-03", sign="Virgo", forecast=False),
    Event(
        "moon-enters-capricorn-2025-03",
        "Moon",
        INGRESS,
        "2025-03",
        sign="Capricorn",
        forecast=False,
    ),
    Event("mars-stations-direct-2025-02", "Mars", STATION, "2025-02", station="direct"),
    Event("venus-stations-retrograde-2025-03", "Venus", STATION, "2025-03", station="retrograde"),
    Event(
        "mercury-stations-retrograde-2025-03", "Mercury", STATION, "2025-03", station="retrograde"
    ),
    Event("mercury-stations-direct-2025-04", "Mercury", STATION, "2025-04", station="direct"),
    Event("venus-stations-direct-2025-04", "Venus", STATION, "2025-04", station="direct"),
    Event("pluto-stations-retrograde-2025-05", "Pluto", STATION, "2025-05", station="retrograde"),
    Event(
        "neptune-stations-retrograde-2025-07", "Neptune", STATION, "2025-07", station="retrograde"
    ),
    Event("saturn-stations-retrograde-2025-07", "Saturn", STATION, "2025-07", station="retrograde"),
    Event(
        "sun-opposes-natal-pluto-2025-02",
        "Sun",
        TRANSIT,
        "2025-02",
        natal="Pluto",
        aspect="opposition",
    ),
)

USNO_CROSS_CHECKS = {"sun-enters-aries-2025-03": "Equinox", "sun-enters-cancer-2025-06": "Solstice"}
"""Cases whose instant USNO also publishes, by the name its seasons table gives the event."""

FAST_BODIES = ("Sun", "Mercury", "Venus", "Mars")
SLOW_BODIES = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")


type Sample = tuple[datetime, float]


def longitudes(body: str, start: datetime, stop: datetime, step: str) -> list[Sample]:
    """Horizons apparent ecliptic longitude of date, unwrapped so it never jumps by 360."""
    text = horizons.observer(BODY_CODES[body], start, "31", stop=stop, step=step)
    samples: list[Sample] = []
    for fields in horizons.rows(text):
        when = datetime.strptime(f"{fields[0]} {fields[1]}", "%Y-%b-%d %H:%M").replace(tzinfo=UTC)
        value = float(fields[-2])
        if samples:
            value += 360.0 * round((samples[-1][1] - value) / 360.0)
        samples.append((when, value))
    return samples


def month_span(month: str) -> tuple[datetime, datetime]:
    first = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
    following = (first + timedelta(days=32)).replace(day=1)
    return first, following


def crossings(
    samples: Sequence[Sample], target: Callable[[float, float], float | None]
) -> list[int]:
    """Indexes ``i`` where the longitude crosses ``target(a, b)`` between rows ``i`` and ``i+1``."""
    return [
        i for i in range(len(samples) - 1) if target(samples[i][1], samples[i + 1][1]) is not None
    ]


def boundary_entering(sign: str) -> Callable[[float, float], float | None]:
    """The sign boundary crossed between two longitudes when the second lies in ``sign``."""
    index = SIGNS.index(sign)

    def target(a: float, b: float) -> float | None:
        if int(b % 360.0 // 30) != index or int(a % 360.0 // 30) == index:
            return None
        edge = 30.0 * (b // 30 if b > a else b // 30 + 1)
        return edge if min(a, b) <= edge <= max(a, b) else None

    return target


def point_reached(point: float) -> Callable[[float, float], float | None]:
    """The unwrapped copy of ``point`` crossed between two longitudes, if any."""

    def target(a: float, b: float) -> float | None:
        edge = point + 360.0 * ((min(a, b) - point) // 360.0 + 1)
        return edge if min(a, b) <= edge <= max(a, b) else None

    return target


def only(found: list[int], what: str) -> int:
    if len(found) != 1:
        raise ValueError(f"{what}: expected one bracket in the month, found {len(found)}")
    return found[0]


def lagrange(samples: Sequence[Sample], when: datetime) -> float:
    origin = samples[0][0]
    x = (when - origin).total_seconds()
    xs = [(t - origin).total_seconds() for t, _ in samples]
    total = 0.0
    for j, (_, y) in enumerate(samples):
        term = y
        for k, xk in enumerate(xs):
            if k != j:
                term *= (x - xk) / (xs[j] - xk)
        total += term
    return total


def bisect(f: Callable[[datetime], float], low: datetime, high: datetime) -> datetime:
    """Root of ``f`` between ``low`` and ``high``, where it changes sign, to a millisecond."""
    f_low = f(low)
    while (high - low).total_seconds() > BISECTION_SECONDS:
        mid = low + (high - low) / 2
        f_mid = f(mid)
        if (f_mid > 0) == (f_low > 0):
            low, f_low = mid, f_mid
        else:
            high = mid
    return low + (high - low) / 2


def crossing_instant(
    body: str, month: str, target: Callable[[float, float], float | None], what: str
) -> datetime:
    first, following = month_span(month)
    daily = longitudes(body, first, following, "1d")
    i = only(crossings(daily, target), what)
    hourly = longitudes(body, daily[i][0] - HOURLY, daily[i + 1][0] + HOURLY, "1h")
    j = only(crossings(hourly, target), what)
    edge = target(hourly[j][1], hourly[j + 1][1])
    assert edge is not None
    window = hourly[max(j - 1, 0) : j + 3]
    return bisect(lambda t: lagrange(window, t) - edge, hourly[j][0], hourly[j + 1][0])


def station_instant(body: str, month: str, kind: str, what: str) -> datetime:
    first, following = month_span(month)
    daily = longitudes(body, first - DAILY, following + DAILY, "1d")
    turning = [
        i
        for i in range(1, len(daily) - 1)
        if (daily[i][1] - daily[i - 1][1] > 0) != (daily[i + 1][1] - daily[i][1] > 0)
        and ((daily[i + 1][1] < daily[i][1]) == (kind == "retrograde"))
        and first <= daily[i][0] < following
    ]
    centre = daily[only(turning, what)][0]
    fine = longitudes(body, centre - STATION_HALF_SPAN, centre + STATION_HALF_SPAN, STATION_STEP)
    span = STATION_HALF_SPAN.total_seconds()
    coefficients = polyfit([((t - centre).total_seconds() / span, y) for t, y in fine])

    def rate(t: datetime) -> float:
        x = (t - centre).total_seconds() / span
        return sum(k * c * x ** (k - 1) for k, c in enumerate(coefficients) if k)

    return bisect(rate, centre - DAILY, centre + DAILY)


def polyfit(points: Sequence[tuple[float, float]]) -> list[float]:
    """Least squares coefficients, constant first, by the normal equations and elimination."""
    n = STATION_DEGREE + 1
    matrix = [[sum(x ** (r + c) for x, _ in points) for c in range(n)] for r in range(n)]
    vector = [sum(y * x**r for x, y in points) for r in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(matrix[r][col]))
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        vector[col], vector[pivot] = vector[pivot], vector[col]
        for r in range(col + 1, n):
            factor = matrix[r][col] / matrix[col][col]
            matrix[r] = [a - factor * b for a, b in zip(matrix[r], matrix[col], strict=True)]
            vector[r] -= factor * vector[col]
    solution = [0.0] * n
    for r in reversed(range(n)):
        tail = sum(matrix[r][c] * solution[c] for c in range(r + 1, n))
        solution[r] = (vector[r] - tail) / matrix[r][r]
    return solution


def natal_longitude(body: str, instant: datetime) -> float:
    return float(horizons.first_row(horizons.observer(BODY_CODES[body], instant, "31"))[-2])


def instant(event: Event) -> datetime:
    if event.kind == INGRESS:
        assert event.sign is not None
        return crossing_instant(event.body, event.month, boundary_entering(event.sign), event.id)
    if event.kind == STATION:
        assert event.station is not None
        return station_instant(event.body, event.month, event.station, event.id)
    assert event.natal is not None and event.aspect is not None
    natal = natal_longitude(event.natal, load_charts()[NATAL_CHART].utc())
    point = (natal + ASPECT_DEGREES[event.aspect]) % 360.0
    return crossing_instant(event.body, event.month, point_reached(point), event.id)


def iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="milliseconds")


def selector(event: Event) -> dict[str, str]:
    """The fields that pick this event out of the forecast timeline."""
    if event.kind == INGRESS:
        assert event.sign is not None
        return {"type": "sign-ingress", "body": event.body, "target": event.sign}
    if event.kind == STATION:
        assert event.station is not None
        return {"type": "retrograde-station", "body": event.body, "station": event.station}
    assert event.natal is not None and event.aspect is not None
    return {
        "type": "transit-aspect",
        "body": event.body,
        "target": event.natal,
        "aspect": event.aspect,
    }


def case(event: Event, when: datetime) -> dict[str, Any]:
    chart = load_charts()[NATAL_CHART]
    day = when.date()
    request: dict[str, Any] = {}
    expected: dict[str, str] = {}
    if event.forecast:
        request["forecast"] = {
            "birthData": {
                "date": chart.date,
                "time": chart.time,
                "timezone": chart.timezone,
                "latitude": chart.latitude,
                "longitude": chart.longitude,
            },
            "startDate": (day - timedelta(days=WINDOW_DAYS)).isoformat(),
            "endDate": (day + timedelta(days=WINDOW_DAYS)).isoformat(),
        }
        request["event"] = selector(event)
        expected[f"{event.body} {event.kind}"] = iso(when)
    if event.kind == INGRESS:
        request["monthly"] = {"year": day.year, "month": day.month, "timezone": 0}
        request["ingress"] = {"planet": event.body, "toSign": event.sign}
        expected[f"{event.body} {INGRESS}{MONTHLY_SUFFIX}"] = iso(when)
    return {"id": event.id, "input": request, "expected": expected}


def usno_instant(year: int, phenomenon: str, month: int) -> str:
    """The USNO seasons table time of one event, UT to the minute as published."""
    doc = json.loads(get_text(USNO_SEASONS_URL, {"year": str(year)}))
    (row,) = [r for r in doc["data"] if r["phenom"] == phenomenon and r["month"] == month]
    hour, minute = (int(part) for part in row["time"].split(":"))
    return iso(datetime(year, month, row["day"], hour, minute, tzinfo=UTC))


def pull() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    cross_checks: list[dict[str, Any]] = []
    for n, event in enumerate(EVENTS, 1):
        print(f"[{n}/{len(EVENTS)}] {event.id}", file=sys.stderr)
        when = instant(event)
        built = case(event, when)
        cases.append(built)
        if event.id in USNO_CROSS_CHECKS:
            published = usno_instant(when.year, USNO_CROSS_CHECKS[event.id], when.month)
            cross_checks.append(
                {
                    "source": "US Naval Observatory seasons",
                    "id": event.id,
                    "input": built["input"],
                    "expected": {f"{event.body} {INGRESS}": published},
                }
            )
    today = datetime.now(UTC).date().isoformat()
    return {
        "format": 1,
        "domain": "forecast",
        "sources": [
            {
                "name": "NASA JPL Horizons",
                "url": horizons.URL,
                "command": "python -m benchmark pull forecast (OBSERVER table, CENTER 500@399, "
                "QUANTITIES 31, daily then hourly or ten minute step, root by bisection)",
                "retrieved": today,
                "licence": horizons.LICENCE,
                "method": "Apparent geocentric ecliptic longitude of date, tabulated daily over "
                "the month of the event to bracket it and hourly around the bracket to locate "
                "it. An ingress or an exact transit is the instant the longitude reaches the "
                "sign boundary or the natal point plus the aspect angle, by bisection on the "
                "cubic through the four hourly rows around the crossing. A station is the "
                "instant the longitude rate is zero, by bisection on the derivative of a "
                "degree six least squares polynomial fitted to four days of rows ten minutes "
                "apart. "
                "Interpolation follows Meeus, Astronomical Algorithms, 2nd edition, chapter 3.",
                "notes": "Times are UT, kept to the millisecond the search resolves; the seven "
                "printed decimals bound them well under a second. Every event is in the past, "
                "where Horizons applies measured delta T. The natal point of the exact transit "
                "is the Horizons longitude at the birth instant of the chart. Sun to Mars use "
                "their "
                "own Horizons centres, Jupiter to Pluto the system barycentres, as for the "
                "planets.",
            },
            {
                "name": "US Naval Observatory seasons",
                "url": USNO_DOC_URL,
                "command": "python -m benchmark pull forecast (GET /api/seasons?year=YYYY)",
                "retrieved": today,
                "licence": "US Naval Observatory data, public domain US government work",
                "method": "Equinox and solstice instants in UT to the minute as published. The "
                "Sun entering Aries and Cancer is the same event, so the two values are kept "
                "as cross checks of the Horizons recomputation, not as references.",
                "applies_to": [f"Sun {INGRESS}", f"Sun {INGRESS}{MONTHLY_SUFFIX}"],
            },
        ],
        "tolerances": TOLERANCES,
        "cases": cases,
        "families": families(cases),
        "cross_checks": cross_checks,
    }


def names(bodies: Sequence[str], kind: str, *, monthly: bool) -> list[str]:
    """Quantity names for ``bodies``, with their monthly table twins for an ingress."""
    found = [f"{b} {kind}" for b in bodies]
    return found + [f"{b} {kind}{MONTHLY_SUFFIX}" for b in bodies] if monthly else found


TOLERANCES: list[dict[str, Any]] = [
    {
        "applies_to": [*names(FAST_BODIES, INGRESS, monthly=True), f"Sun {TRANSIT}"],
        "value": 60,
        "unit": "seconds",
        "why": "A vendor-neutral pass bar, not sized to any one API. At these events the Sun, "
        "Mercury, Venus and Mars move at least half a degree a day, so a minute is at least an "
        "arcsecond of motion: wide enough for the arcsecond level disagreement between two good "
        "ephemerides, tight enough to fail a crossing read off a sampled table or a longitude "
        "in the wrong frame. The monthly table prints whole minutes, which takes up to half of "
        "this band. An exact transit also carries the natal longitude, so a natal error shows "
        "here as time.",
    },
    {
        "applies_to": [f"Moon {INGRESS}{MONTHLY_SUFFIX}"],
        "value": 60,
        "unit": "seconds",
        "why": "The Moon moves about 13 degrees a day, so a minute is about 33 arcseconds, inside "
        "the band its position is held to. The table prints whole minutes, which takes up to "
        "half of this band.",
    },
    {
        "applies_to": names(SLOW_BODIES, INGRESS, monthly=True),
        "value": 600,
        "unit": "seconds",
        "why": "Jupiter to Pluto move between a few hundredths and a quarter of a degree a day, "
        "so the same arcsecond of legitimate disagreement is tens of seconds to over ten "
        "minutes of time. Ten minutes is under one arcsecond of Neptune motion and still fails "
        "a crossing read off an hourly or daily table.",
    },
    {
        "applies_to": names(FAST_BODIES, STATION, monthly=False),
        "value": 60,
        "unit": "seconds",
        "why": "A station is the instant the longitude rate is zero, the vertex of a near "
        "parabola, so its time is set by the rate, not the position: within a minute of a "
        "Mars station the longitude changes by a hundred thousandth of an arcsecond. Mercury, "
        "Venus and Mars turn fast enough that a minute is a rate disagreement of 0.03 "
        "arcseconds a day for Mars to 0.35 for Mercury, which two good ephemerides stay "
        "inside.",
    },
    {
        "applies_to": names(SLOW_BODIES, STATION, monthly=False),
        "value": 600,
        "unit": "seconds",
        "why": "Saturn to Pluto turn so slowly, their rate changing by 0.0005 to 0.002 degrees a "
        "day each day, "
        "that a rate disagreement of a thousandth of an arcsecond a day moves the station by "
        "up to a minute, so the band is wider than for the fast bodies. Ten minutes still fails "
        "a station taken from a sampled table, and a longitude without the precession of date, "
        "which moves a Pluto station by about two hours.",
    },
]

FAMILY_LABELS = {
    INGRESS: "Sign ingress instants",
    STATION: "Station instants",
    TRANSIT: "Exact transit instant",
}
"""Reader-facing group of each event kind, for the ``families`` block once the schema carries
it; ``families`` builds the block from the pulled cases."""


def families(cases: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every quantity of the cases under the label of its event kind, in case order."""
    grouped: dict[str, list[str]] = {kind: [] for kind in FAMILY_LABELS}
    for built in cases:
        for quantity in built["expected"]:
            kind = quantity.removesuffix(MONTHLY_SUFFIX).split()[-1]
            if quantity not in grouped[kind]:
                grouped[kind].append(quantity)
    return [{"label": FAMILY_LABELS[k], "quantities": q} for k, q in grouped.items() if q]
