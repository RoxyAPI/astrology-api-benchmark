"""Rebuild ``references.json`` from the biorhythm definition, with no network access.

Each primary cycle is a sine wave of the number of days since birth ``t``: physical
``sin(2 pi t / 23)``, emotional ``sin(2 pi t / 28)``, intellectual ``sin(2 pi t / 33)``. Every
cycle starts at zero on the birth date. The day count is the difference of the two calendar
dates, so a date carries no time of day and no time zone.

Two cycle readings are compared per cycle: the percentage from -100 to 100 rounded to the nearest
whole number, and the raw sine rounded to four decimals, which is how the API publishes them.
Both are discrete printed values, so they are compared exactly.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import pi, sin
from typing import Any

PERIODS = {"physical": 23, "emotional": 28, "intellectual": 33}
"""Cycle length in days, as published for the three primary cycles."""

TRIPLE_RETURN = 21_252
"""Days until all three cycles are at zero together: 23 x 28 x 33, the periods being coprime."""

# (case id, birth date, target date, why the case is here)
CASES = (
    ("birth-day", "1990-07-15", "1990-07-15", "day zero, every cycle at zero"),
    ("before-anniversary", "1990-07-15", "2026-04-10", "target before the birthday of its year"),
    ("on-anniversary", "1990-07-15", "2026-07-15", "target on the birthday itself"),
    ("leap-day-birth", "2000-02-29", "2025-03-01", "born on a leap day, target in a common year"),
    ("leap-day-span", "2000-02-29", "2024-02-29", "leap day to leap day, twenty-four years apart"),
    ("across-leap-day", "2023-12-31", "2024-03-01", "a short span that includes 29 February"),
    ("long-span", "1930-01-01", "2026-10-01", "a span of more than ninety-six years"),
    (
        "century-span",
        "1900-03-01",
        "2000-01-01",
        "a span of a century across the 1900 non-leap year",
    ),
    (
        "elderly-birth",
        "1946-06-14",
        "2026-10-09",
        "a mid twentieth century birth, eight decades on",
    ),
)


def day_count(birth: str, target: str) -> int:
    """Whole calendar days from the birth date to the target date."""
    return (date.fromisoformat(target) - date.fromisoformat(birth)).days


def cycle_values(days: int) -> dict[str, float]:
    """The raw sine of every primary cycle after ``days`` days."""
    return {name: sin(2 * pi * days / period) for name, period in PERIODS.items()}


def percent(raw: float) -> int:
    """Percentage position, -100 to 100, to the nearest whole number."""
    return round(raw * 100)


def raw_text(raw: float) -> str:
    """The raw sine to four decimals as text, with no negative zero."""
    return f"{raw:.4f}".replace("-0.0000", "0.0000")


def quantities(birth: str, target: str) -> dict[str, str | int]:
    days = day_count(birth, target)
    expected: dict[str, str | int] = {"days_since_birth": days}
    for name, raw in cycle_values(days).items():
        expected[f"{name}_percent"] = percent(raw)
        expected[f"{name}_raw"] = raw_text(raw)
    return expected


def triple_return_target(birth: str) -> str:
    return (date.fromisoformat(birth) + timedelta(days=TRIPLE_RETURN)).isoformat()


def pull() -> dict[str, Any]:
    cases = [
        {
            "id": case_id,
            "input": {"birthDate": birth, "targetDate": target},
            "expected": quantities(birth, target),
        }
        for case_id, birth, target, _ in CASES
    ]
    return_target = triple_return_target("1990-07-15")
    cases.append(
        {
            "id": "triple-return",
            "input": {"birthDate": "1990-07-15", "targetDate": return_target},
            "expected": quantities("1990-07-15", return_target),
        }
    )
    return {
        "format": 1,
        "domain": "biorhythm",
        "sources": [
            {
                "name": "Cleve Moler, Biorhythms, MathWorks blog",
                "url": "https://blogs.mathworks.com/cleve/2012/06/11/biorhythms-2/",
                "command": "python -m benchmark pull biorhythm",
                "retrieved": "2026-10-09",
                "licence": "Published definition, facts only, cited",
                "method": (
                    "Recomputed from the definition: physical sin(2 pi t / 23), emotional "
                    "sin(2 pi t / 28), intellectual sin(2 pi t / 33), where t is the number of "
                    "days since birth. The percentage is 100 times the sine rounded to the "
                    "nearest whole number and the raw value is the sine rounded to four "
                    "decimals."
                ),
                "notes": (
                    "The day count is the difference of two calendar dates, with no time of "
                    "day and no time zone. Only the three primary cycles carry a published "
                    "period, so no other cycle is checked."
                ),
            },
            {
                "name": "US Patent 4,240,153, Biorhythm display device, USPTO",
                "url": "https://patents.google.com/patent/US4240153A/en",
                "retrieved": "2026-10-09",
                "licence": "US government patent record, facts only, cited",
                "method": (
                    "Read for the same three periods of 23, 28 and 33 days and for the rule "
                    "that the cycles are set from the number of days elapsed since the birth "
                    "date, which the day count of each case follows."
                ),
                "applies_to": ["days_since_birth"],
            },
        ],
        "families": [
            {
                "label": "Physical, emotional and intellectual cycles",
                "quantities": [
                    "days_since_birth",
                    "physical_percent",
                    "physical_raw",
                    "emotional_percent",
                    "emotional_raw",
                    "intellectual_percent",
                    "intellectual_raw",
                ],
            },
        ],
        "tolerances": [
            {
                "applies_to": ["days_since_birth"],
                "value": 0,
                "unit": "days",
                "why": "A calendar day count is an integer: a miss is a wrong day",
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": (
                    "The percentage is published as a whole number and the raw sine to four "
                    "decimals, so the recomputed value rounded the same way must match exactly."
                ),
            },
        ],
        "cases": cases,
    }
