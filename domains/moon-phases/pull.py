"""Rebuild ``references.json`` from the U.S. Naval Observatory primary moon phase tables.

The Astronomical Applications Department publishes the instant of every new moon, first quarter,
full moon and last quarter in Universal Time, one JSON document per calendar year. The API under
test publishes the calendar date of each phase, not the instant, so the comparison is a date: the
Universal Time date of the published instant, unit days, tolerance 0.

Most cases sit well away from midnight Universal Time, where the date does not depend on how a
provider rounds an instant to a day. Two sit within an hour of it, one on each side, so a provider
that shifts the date by a time zone fails them. Run it with
``uv run python -m benchmark pull moon-phases``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from benchmark.fetch import get_text

USNO_URL = "https://aa.usno.navy.mil/api/moon/phases/year"

# USNO phase name to the phase name the API prints.
API_PHASE = {
    "New Moon": "New Moon",
    "First Quarter": "First Quarter Moon",
    "Full Moon": "Full Moon",
    "Last Quarter": "Third Quarter Moon",
}

LEAD_DAYS = 3
"""The request starts this many days before the phase, so the phase is the first one returned."""
COUNT = 2
CLEAR_MINUTES = 180
"""A normal case sits at least this far from midnight Universal Time."""
BOUNDARY_MINUTES = 60
"""A boundary case sits within this many minutes of midnight Universal Time."""

# (case id, year, month, day, USNO phase, why the case is here)
CLEAR = (
    ("new-1969-07-14", 1969, 7, 14, "New Moon", "a new moon in the month of the first landing"),
    ("first-1969-07-22", 1969, 7, 22, "First Quarter", "a first quarter eight days later"),
    ("last-1988-06-07", 1988, 6, 7, "Last Quarter", "a last quarter in the late twentieth century"),
    ("full-1988-11-23", 1988, 11, 23, "Full Moon", "a full moon in the late afternoon"),
    ("full-2000-07-16", 2000, 7, 16, "Full Moon", "a full moon at midday in the year 2000"),
    ("first-2012-01-01", 2012, 1, 1, "First Quarter", "a quarter on the first day of a year"),
    ("full-2012-06-04", 2012, 6, 4, "Full Moon", "a full moon in a leap year"),
    ("last-2019-03-28", 2019, 3, 28, "Last Quarter", "a last quarter in the early morning"),
    ("new-2019-10-28", 2019, 10, 28, "New Moon", "a new moon in the early morning"),
)
BOUNDARY = (
    (
        "new-2023-12-12",
        2023,
        12,
        12,
        "New Moon",
        "a new moon 28 minutes before midnight UT: a provider ahead of UT reads it a day late",
    ),
    (
        "full-2023-12-27",
        2023,
        12,
        27,
        "Full Moon",
        "a full moon 33 minutes after midnight UT: a provider behind UT reads it a day early",
    ),
)


def minutes_from_midnight(time: str) -> int:
    """Distance of an ``HH:MM`` Universal Time reading from the nearest midnight, in minutes."""
    hours, minutes = (int(part) for part in time.split(":"))
    of_day = hours * 60 + minutes
    return min(of_day, 24 * 60 - of_day)


def phase_table(year: int) -> dict[date, tuple[str, str]]:
    """The USNO phases of one year by Universal Time date: phase name and ``HH:MM``."""
    document = json.loads(get_text(USNO_URL, {"year": str(year)}))
    return {
        date(row["year"], row["month"], row["day"]): (row["phase"], row["time"])
        for row in document["phasedata"]
    }


def build_case(
    tables: dict[int, dict[date, tuple[str, str]]],
    row: tuple[str, int, int, int, str, str],
    *,
    boundary: bool,
) -> dict[str, Any]:
    case_id, year, month, day, usno_phase, _ = row
    when = date(year, month, day)
    table = tables.setdefault(year, phase_table(year))
    phase, time = table[when]
    if phase != usno_phase:
        raise ValueError(f"{case_id}: USNO lists {phase} on {when}, not {usno_phase}")
    distance = minutes_from_midnight(time)
    if boundary and distance > BOUNDARY_MINUTES:
        raise ValueError(f"{case_id}: {time} UT is not within an hour of midnight")
    if not boundary and distance < CLEAR_MINUTES:
        raise ValueError(f"{case_id}: {time} UT is too close to midnight for a clear case")
    return {
        "id": case_id,
        "input": {
            "startDate": (when - timedelta(days=LEAD_DAYS)).isoformat(),
            "count": COUNT,
            "phase": API_PHASE[usno_phase],
        },
        "expected": {"date": when.isoformat()},
    }


def pull() -> dict[str, Any]:
    tables: dict[int, dict[date, tuple[str, str]]] = {}
    cases = [build_case(tables, row, boundary=False) for row in CLEAR]
    cases += [build_case(tables, row, boundary=True) for row in BOUNDARY]
    return {
        "format": 1,
        "domain": "moon-phases",
        "sources": [
            {
                "name": "U.S. Naval Observatory Astronomical Applications moon phase service",
                "url": "https://aa.usno.navy.mil/data/api",
                "command": "python -m benchmark pull moon-phases (one JSON document per year)",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "licence": (
                    "U.S. government work, public domain; "
                    "cite the Astronomical Applications Department"
                ),
                "method": (
                    "The primary phases of each listed year are read from the year endpoint: the "
                    "phase name and the instant in Universal Time. The expected value is the "
                    "calendar date of that instant in Universal Time."
                ),
                "notes": (
                    "The API under test names no time zone for this list and carries no "
                    "parameter for one, so its dates are compared as Universal Time dates, the "
                    "zone its sibling phase endpoint documents as its default. Two cases sit "
                    "within an hour of midnight Universal Time, one on each side, to prove that "
                    "convention; the others sit at least three hours from it."
                ),
                "applies_to": "*",
            }
        ],
        "families": [
            {"label": "Phase dates", "quantities": ["date"]},
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": 0,
                "unit": "days",
                "why": (
                    "A phase date is a calendar day. Away from midnight a one day miss is a "
                    "wrong phase; within an hour of midnight it is a wrong time zone."
                ),
            }
        ],
        "cases": cases,
    }
