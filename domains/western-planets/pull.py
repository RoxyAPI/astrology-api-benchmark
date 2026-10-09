"""Regenerate ``references.json`` from NASA JPL Horizons.

For every chart in ``data/charts.csv`` this asks the Horizons API for the apparent geocentric
ecliptic longitude of each body at the exact instant of the chart. Longitudes keep the seven
decimal degrees Horizons prints (about 0.0004 arcseconds) and are never rounded further. Run it with
``uv run python -m benchmark pull western-planets``; nothing else in the repo contacts Horizons.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from benchmark import horizons
from benchmark.schema import load_charts

HORIZONS_DECIMALS = 7

# Sun to Mars by their own Horizons centres. Jupiter to Pluto by the system barycentres 5 to 9:
# the planetary ephemeris integrates the barycentres, and the planet centres 599 to 999 come from
# separate satellite solutions that sit off it. Chiron is the small body 2060 (the trailing
# semicolon selects the body rather than a search).
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
    "Chiron": "2060;",
}

SMALL_BODY = "Chiron"
"""The one body from the Horizons small-body integration rather than the planetary ephemeris."""

PLANET_BAND_ARCSEC = 36
MOON_BAND_ARCSEC = 72


def pull() -> dict[str, Any]:
    charts = load_charts()
    cases: list[dict[str, Any]] = []
    total = len(charts) * len(BODY_CODES)
    done = 0
    for chart in charts.values():
        instant = chart.utc()
        expected: dict[str, float] = {}
        for body, command in BODY_CODES.items():
            done += 1
            print(f"[{done}/{total}] {chart.id} {body}", file=sys.stderr)
            # Observer ecliptic longitude is the second-to-last field of quantity 31.
            longitude = float(horizons.first_row(horizons.observer(command, instant, "31"))[-2])
            expected[body] = round(longitude % 360.0, HORIZONS_DECIMALS)
        cases.append({"id": chart.id, "chart": chart.id, "expected": expected})
    return {
        "format": 1,
        "domain": "western-planets",
        "sources": [
            {
                "name": "NASA JPL Horizons",
                "url": horizons.URL,
                "command": "python -m benchmark pull western-planets (OBSERVER table, "
                "CENTER 500@399, QUANTITIES 31, one minute step)",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "licence": horizons.LICENCE,
                "method": "Apparent geocentric ecliptic longitude of date at the chart instant "
                "converted to UT, read from the Observer Ecliptic Longitude column, seven "
                "decimal degrees as printed.",
                "notes": "Sun to Mars use their own Horizons centres. Jupiter to Pluto use the "
                "Horizons system barycentres 5 to 9: the planetary ephemeris integrates the "
                "system barycentres, while the planet centres come from separate satellite "
                "solutions that sit off it by thousands of kilometres.",
                "applies_to": [body for body in BODY_CODES if body != SMALL_BODY],
            },
            {
                "name": "NASA JPL Horizons small-body integration",
                "url": horizons.URL,
                "command": "python -m benchmark pull western-planets (OBSERVER table, "
                "CENTER 500@399, QUANTITIES 31, one minute step)",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "licence": horizons.LICENCE,
                "method": "Apparent geocentric ecliptic longitude of the small body 2060 Chiron "
                "at the chart instant converted to UT, which Horizons integrates on demand from "
                "the initial conditions of its orbit solution, read from the same column as the "
                "planets.",
                "applies_to": [SMALL_BODY],
            },
        ],
        "families": [
            {
                "label": "Sun, Moon, planets and Chiron",
                "quantities": [
                    "Sun",
                    "Moon",
                    "Mercury",
                    "Venus",
                    "Mars",
                    "Jupiter",
                    "Saturn",
                    "Uranus",
                    "Neptune",
                    "Pluto",
                    "Chiron",
                ],
            },
        ],
        "tolerances": [
            {
                "applies_to": ["Moon"],
                "value": MOON_BAND_ARCSEC,
                "unit": "arcsec",
                "why": "The Moon moves about 13 degrees a day, so this absorbs a couple of "
                "minutes of birth time interpretation. A vendor-neutral pass bar, not sized to "
                "any one API.",
            },
            {
                "applies_to": "*",
                "value": PLANET_BAND_ARCSEC,
                "unit": "arcsec",
                "why": "A vendor-neutral pass bar, not sized to any one API. Wide enough for the "
                "legitimate arcsecond level disagreement between two good ephemeris "
                "implementations, tight enough to fail a geometric rather than an apparent "
                "ephemeris, a wrong timezone resolution or a wrong epoch element set. Read the "
                "per body maxima for regressions: a body drifting from 0.1 to 20 arcseconds "
                "still passes.",
            },
        ],
        "cases": cases,
    }
