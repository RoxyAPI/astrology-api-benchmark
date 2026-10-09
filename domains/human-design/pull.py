"""Rebuild ``references.json``: the Human Design Design moment from NASA JPL Horizons, and the
Sun and Earth gates, lines and profile by the published rules of the system.

- The Personality side is the birth instant. The Design side is the instant the Sun stood 88
  degrees of its own movement before the natal Sun (Ra Uru Hu, Introduction to the Human Design
  System, International Human Design School, pages 3 and 4; Jovian Archive repeats it as 88
  degrees of solar movement). It is solved here on the apparent geocentric ecliptic longitude
  of date from Horizons by Newton steps on the Sun rate, then interpolated inside a one minute
  Horizons window, so the instant is exact to well under a second; never as 88 calendar days.
- The Rave Mandala tiles the ecliptic with 64 gates of 5 deg 37 min 30 sec, six lines each, in
  the fixed order of ``WHEEL`` starting with gate 41 at 2 deg Aquarius, longitude 302. Jovian
  Archive dates the Sun entering gate 41 to 22 January 2024, 13:18 UTC, which this pull checks
  against Horizons to the minute; the published degree table of every gate is pinned by a test.
- The Earth is the point opposite the Sun. The profile is the Personality Sun line over the
  Design Sun line (Jovian Archive, Understanding Your Human Design Profile).

Run it with ``uv run python -m benchmark pull human-design``; nothing else contacts a source.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from benchmark import horizons
from benchmark.schema import load_charts

SUN = "10"
DESIGN_ARC = 88.0
"""Degrees of solar arc between the Design Sun and the Personality Sun."""
SOLAR_DAILY_ARC = 0.9856
"""Mean degrees of solar motion a day; only seeds the search."""

WHEEL = (
    41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42, 3,
    27, 24, 2, 23, 8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56,
    31, 33, 7, 4, 29, 59, 40, 64, 47, 6, 46, 18, 48, 57, 32, 50,
    28, 44, 1, 43, 14, 34, 9, 5, 26, 11, 10, 58, 38, 54, 61, 60,
)  # fmt: skip
"""The Rave Mandala gate order in increasing ecliptic longitude, from gate 41."""
WHEEL_START = 302.0
"""Ecliptic longitude where gate 41 line 1 begins: 2 degrees Aquarius."""
GATE_SPAN = 360 / 64
LINE_SPAN = GATE_SPAN / 6

RAVE_NEW_YEAR = datetime(2024, 1, 22, 13, 18)
"""Jovian Archive: the Sun enters gate 41, the Rave New Year, at this minute (UTC)."""

CHARTS = ("einstein", "monroe", "jfk", "obama", "musk", "sydney_2010", "ny_dst_fall")
"""Corpus charts across 1879 to 2010, both hemispheres and an ambiguous local hour. On each, 88
calendar days instead of 88 degrees of arc moves the Design Sun to another line."""

LINE_MARGIN_ARCSEC = 10
"""Every reference Sun sits at least this far from a line edge, so an implementation inside the
arcsecond level of the ephemeris can never land on the other side by rounding."""
EDGE_ARCSEC = 15
"""The edge cases put a Sun this far past a line edge: an error larger than this flips it."""

SIDES = ("personality", "design")
GATE_QUANTITIES = [
    f"{s} {b} {q}" for s in SIDES for b in ("Sun", "Earth") for q in ("gate", "line")
]
FAMILIES = [
    {"label": "Design instant", "quantities": ["design instant"]},
    {
        "label": "Personality and design Sun and Earth gates and lines",
        "quantities": GATE_QUANTITIES,
    },
    {"label": "Profile", "quantities": ["profile"]},
]
"""Reader-facing groups of the quantities for the coverage map and the README."""

INSTANT_BAND_SECONDS = 60
EARTH_OFFSET = 180.0


def wrap180(angle: float) -> float:
    return (angle + 180) % 360 - 180


def gate_line(longitude: float) -> tuple[int, int]:
    """The Rave Mandala gate and line of an ecliptic longitude in degrees."""
    offset = (longitude - WHEEL_START) % 360
    index = int(offset // GATE_SPAN)
    return WHEEL[index], int(offset % GATE_SPAN // LINE_SPAN) + 1


def line_margin_arcsec(longitude: float) -> float:
    """Distance to the nearest line edge, arcseconds."""
    within = (longitude - WHEEL_START) % LINE_SPAN
    return min(within, LINE_SPAN - within) * 3600


def sun_window(start: datetime) -> tuple[float, float]:
    """Apparent Sun longitude at ``start`` (UT, whole second) and one minute later, degrees."""
    text = horizons.observer(
        SUN,
        start,
        "31",
        extra={"TIME_TYPE": "'UT'", "ANG_FORMAT": "'DEG'", "EXTRA_PREC": "'YES'"},
    )
    first, last = horizons.rows(text)[:2]
    return float(first[-2]), float(last[-2])


def sun_reaches(longitude: float, seed: datetime) -> datetime:
    """The UT instant near ``seed`` at which the apparent Sun reaches ``longitude``."""
    instant = seed.replace(microsecond=0)
    for _ in range(8):
        start, end = sun_window(instant)
        rate = wrap180(end - start) / 60
        offset = wrap180(longitude - start) / rate
        if 0 <= offset < 60:
            return instant + timedelta(seconds=offset)
        instant += timedelta(seconds=math.floor(offset))
    raise ValueError(f"no convergence on the Sun reaching {longitude} near {seed}")


def sun_at(instant: datetime) -> float:
    """Apparent Sun longitude at a UT instant given to the second."""
    return sun_window(instant)[0]


def expected_values(birth: datetime) -> dict[str, Any]:
    """Reference values for a birth at the UT instant ``birth``."""
    natal = sun_at(birth)
    design_sun = (natal - DESIGN_ARC) % 360
    seed = birth - timedelta(days=DESIGN_ARC / SOLAR_DAILY_ARC)
    design = sun_reaches(design_sun, seed)
    values: dict[str, Any] = {
        "design instant": design.replace(tzinfo=UTC).isoformat(timespec="milliseconds"),
    }
    for side, sun in (("personality", natal), ("design", design_sun)):
        margin = line_margin_arcsec(sun)
        if margin < LINE_MARGIN_ARCSEC:
            raise ValueError(f"{birth}: {side} Sun {margin:.1f} arcsec from a line edge")
        for body, longitude in (("Sun", sun), ("Earth", sun + EARTH_OFFSET)):
            values[f"{side} {body} gate"], values[f"{side} {body} line"] = gate_line(longitude)
    values["profile"] = f"{values['personality Sun line']}/{values['design Sun line']}"
    calendar_design = sun_at(birth - timedelta(days=DESIGN_ARC))
    values["_calendar_line"] = gate_line(calendar_design)
    return values


def inline_input(instant: datetime) -> dict[str, Any]:
    return {
        "date": instant.strftime("%Y-%m-%d"),
        "time": instant.strftime("%H:%M:%S"),
        "timezone": 0,
    }


def edge_birth(seed: datetime, side: str) -> datetime:
    """A whole-second birth near ``seed`` whose Personality or Design Sun sits ``EDGE_ARCSEC``
    past a line edge."""
    sun = sun_at(seed)
    point = sun - DESIGN_ARC if side == "design" else sun
    edge = WHEEL_START + math.ceil((point - WHEEL_START) / LINE_SPAN) * LINE_SPAN
    target = edge + EDGE_ARCSEC / 3600 + (DESIGN_ARC if side == "design" else 0)
    birth = sun_reaches(target % 360, seed)
    return birth.replace(microsecond=0) + timedelta(seconds=1)


def pull() -> dict[str, Any]:
    crossing = sun_reaches(WHEEL_START, RAVE_NEW_YEAR - timedelta(minutes=5))
    if abs((crossing - RAVE_NEW_YEAR).total_seconds()) > 60:
        raise ValueError(f"Horizons puts the Sun at 302 degrees at {crossing}, not near 13:18")
    print(f"gate 41 entry {crossing.isoformat()} UT", file=sys.stderr)

    cases: list[dict[str, Any]] = []
    charts = load_charts()
    for chart_id in CHARTS:
        print(chart_id, file=sys.stderr)
        values = expected_values(charts[chart_id].utc().replace(tzinfo=None))
        calendar = values.pop("_calendar_line")
        if calendar == (values["design Sun gate"], values["design Sun line"]):
            raise ValueError(f"{chart_id}: 88 calendar days keeps the Design Sun line")
        cases.append({"id": chart_id, "chart": chart_id, "expected": values})

    anchor = RAVE_NEW_YEAR + timedelta(minutes=7)
    edges = {
        "rave-new-year-2024": anchor,
        "design-line-edge": edge_birth(datetime(1990, 7, 15, 12), "design"),
        "personality-line-edge": edge_birth(datetime(1975, 3, 9, 6), "personality"),
    }
    for case_id, birth in edges.items():
        print(case_id, file=sys.stderr)
        values = expected_values(birth)
        values.pop("_calendar_line")
        cases.append({"id": case_id, "input": inline_input(birth), "expected": values})

    cross_checks = [
        {
            "id": "rave-new-year-2024",
            "source": "Jovian Archive",
            "input": inline_input(anchor),
            "expected": {"personality Sun gate": 41, "personality Sun line": 1},
        }
    ]
    return document(cases, cross_checks, crossing)


def document(
    cases: list[dict[str, Any]], cross_checks: list[dict[str, Any]], crossing: datetime
) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    discrete = GATE_QUANTITIES
    return {
        "format": 1,
        "domain": "human-design",
        "sources": [
            {
                "name": "NASA JPL Horizons",
                "url": horizons.URL,
                "command": "python -m benchmark pull human-design (OBSERVER tables of the "
                "geocentric Sun, QUANTITIES 31, one minute windows at whole UT seconds)",
                "retrieved": today,
                "licence": horizons.LICENCE,
                "method": "Apparent geocentric ecliptic longitude of date of the Sun at birth; "
                "the Design moment root found by Newton steps on the Sun rate until the Sun "
                "stands 88 degrees behind the natal Sun, then interpolated inside the bracketing "
                "minute. Gates and lines follow from these longitudes by the Rave Mandala.",
                "notes": "Horizons puts the Sun at 302 degrees, the start of gate 41, at "
                f"{crossing.strftime('%Y-%m-%d %H:%M:%S')} UT, inside the minute Jovian "
                "Archive publishes for the Rave New Year.",
            },
            {
                "name": "Introduction to the Human Design System",
                "url": "https://www.ihdschool.com/resources/free-library",
                "citation": "Ra Uru Hu, Introduction to the Human Design System, International "
                "Human Design School, free edition: pages 3 and 4, the Design calculation 88 "
                "degrees of the movement of the Sun before birth",
                "retrieved": today,
                "licence": "Published by the International Human Design School; the rule is "
                "cited, no text is reproduced",
                "method": "The Design side is computed at the instant the Sun stood 88 degrees "
                "of solar arc before its natal longitude, never 88 calendar days.",
                "applies_to": ["design instant", *discrete[4:]],
            },
            {
                "name": "Jovian Archive",
                "url": "https://jovianarchive.com/blogs/transits-global-cycles/"
                "the-rave-new-year-stage-1-and-2",
                "retrieved": today,
                "licence": "Jovian Archive publication; facts cited, no text reproduced",
                "method": "The Sun enters gate 41, the first gate of the Rave Mandala, on 22 "
                "January 2024 at 13:18 UTC, fixing the wheel start at 2 degrees Aquarius. The "
                "profile is the Personality Sun line over the Design Sun line "
                "(https://jovianarchive.com/blogs/chart-interpretations-components/"
                "understanding-your-human-design-profile).",
                "applies_to": [*discrete, "profile"],
            },
            {
                "name": "Human Design Gates by Zodiac Degrees",
                "url": "https://bonniesorsby.com/human-design-gates-by-degree/",
                "retrieved": today,
                "licence": "Published table; the degree of each gate is cited as a fact",
                "method": "The opening degree and minute of all 64 gates in zodiac order, which "
                "a test pins against the wheel order and the 5 deg 37 min 30 sec gate.",
                "applies_to": discrete,
            },
        ],
        "tolerances": [
            {
                "applies_to": ["design instant"],
                "value": INSTANT_BAND_SECONDS,
                "unit": "seconds",
                "why": "The Sun moves about one arcsecond in 24 seconds, so this is about 2.5 "
                "arcseconds of solar arc: room for two good ephemerides and their nutation and "
                "aberration models, while 88 calendar days, a mean Sun or a wrong timezone "
                "misses by hours.",
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": "Gates, lines and the profile are discrete: the Rave Mandala applied to "
                "the longitude gives the value or it does not. Every reference Sun sits at least "
                f"{LINE_MARGIN_ARCSEC} arcseconds inside its line.",
            },
        ],
        "cases": cases,
        "cross_checks": cross_checks,
        "families": FAMILIES,
    }
