"""Rebuild ``references.json`` from the calendar definition, with no network access.

Every expected value is recomputed from the Goodman-Martinez-Thompson definition: the Julian Day
Number of the Long Count epoch 0.0.0.0.0 (4 Ajaw 8 Kumku) is 584283. Dates are proleptic
Gregorian for every year, extended backwards unchanged through the 1582 reform, which is how the
API defines its input. A converter that reads dates before 15 October 1582 as Julian disagrees
with it by ten or eleven days; that is a difference of input convention, not of arithmetic.

The second source is a published converter. Its values were transcribed by hand from its form
output into ``CONVERTER_VALUES`` below, and a test asserts the recomputation reproduces them.
"""

from __future__ import annotations

from typing import Any

CORRELATION = 584283
"""Julian Day Number of the epoch 13.0.0.0.0 = 4 Ajaw 8 Kumku, the GMT correlation constant."""

CORRELATION_ID = "gmt-584283"

DAY_SIGNS = (
    "imix", "ik", "akbal", "kan", "chikchan", "kimi", "manik", "lamat", "muluk", "ok",
    "chuwen", "eb", "ben", "ix", "men", "kib", "kaban", "etznab", "kawak", "ajaw",
)  # fmt: skip
"""The twenty Tzolkin day signs in cycle order, as lowercase ASCII machine ids."""

HAAB_MONTHS = (
    "pop", "wo", "sip", "sotz", "sek", "xul", "yaxkin", "mol", "chen", "yax",
    "sak", "keh", "mak", "kankin", "muwan", "pax", "kayab", "kumku", "wayeb",
)  # fmt: skip
"""Eighteen months of twenty days, then Wayeb of five, in year order."""

EPOCH_TZOLKIN_NUMBER = 4
EPOCH_TZOLKIN_SIGN = DAY_SIGNS.index("ajaw")
EPOCH_HAAB_DAY_OF_YEAR = HAAB_MONTHS.index("kumku") * 20 + 8
"""8 Kumku counted from 0 Pop: 17 months of 20 days plus 8."""

LONG_COUNT_PLACES = (144_000, 7_200, 360, 20, 1)
"""Days in a baktun, katun, tun, winal and kin. A winal holds 20 kin; a tun holds 18 winal."""

# (case id, ISO date, why the case is here)
DATES = (
    ("creation-era", "2012-12-21", "13.0.0.0.0, the best known period ending"),
    ("day-before-creation-era", "2012-12-20", "12.19.19.17.19, every place at its maximum"),
    ("millennium", "2000-01-01", "a year 2000 reference date"),
    ("obama-birth", "1961-08-04", "a mid twentieth century date"),
    ("einstein-birth", "1879-03-14", "a nineteenth century date"),
    ("wayeb-day", "2000-04-02", "a day in Wayeb, the five day month that closes the Haab year"),
    ("classic-era", "0600-01-01", "a Classic period date, well before the 1582 reform"),
    ("pre-reform", "1000-01-01", "a date before 15 October 1582, read as proleptic Gregorian"),
)

CONVERTER_VALUES: dict[str, tuple[str, str, int, str, int]] = {
    "creation-era": ("13.0.0.0.0", "ajaw", 4, "kankin", 3),
    "day-before-creation-era": ("12.19.19.17.19", "kawak", 3, "kankin", 2),
    "millennium": ("12.19.6.15.2", "ik", 11, "kankin", 10),
    "obama-birth": ("12.17.7.15.13", "ben", 9, "xul", 11),
    "einstein-birth": ("12.13.4.5.0", "ajaw", 11, "pax", 13),
    "wayeb-day": ("12.19.7.1.14", "ix", 12, "wayeb", 2),
    "classic-era": ("9.8.6.8.3", "akbal", 1, "muwan", 16),
    "pre-reform": ("10.8.12.5.0", "ajaw", 4, "wo", 8),
}
"""Long Count, Tzolkin sign and number, Haab month and day, as the converter printed them."""


def julian_day_number(year: int, month: int, day: int) -> int:
    """Julian Day Number at noon of a proleptic Gregorian date, years 1 and later.

    Fliegel and Van Flandern, "A machine algorithm for processing calendar dates",
    Communications of the ACM 11 (10), 1968, p. 657. The one division of a possibly
    negative operand, (month - 14) / 12, truncates toward zero, so it is written out.
    """
    a = -1 if month <= 2 else 0
    return (
        (1461 * (year + 4800 + a)) // 4
        + (367 * (month - 2 - 12 * a)) // 12
        - (3 * ((year + 4900 + a) // 100)) // 4
        + day
        - 32075
    )


def long_count(days: int) -> str:
    """Long Count digits of a day count; the winal stays below 18 because a tun is 360 days."""
    places = []
    for size in LONG_COUNT_PLACES:
        places.append(days // size)
        days %= size
    return ".".join(str(p) for p in places)


def quantities(iso_date: str) -> dict[str, str | int]:
    """Every compared quantity for one proleptic Gregorian date."""
    year, month, day = (int(p) for p in iso_date.split("-"))
    jdn = julian_day_number(year, month, day)
    days = jdn - CORRELATION
    if days < 0:
        raise ValueError(f"{iso_date} precedes the epoch")
    haab = (EPOCH_HAAB_DAY_OF_YEAR + days) % 365
    return {
        "long_count": long_count(days),
        "days_since_epoch": days,
        "julian_day_number": jdn,
        "tzolkin_sign": DAY_SIGNS[(EPOCH_TZOLKIN_SIGN + days) % 20],
        "tzolkin_number": (EPOCH_TZOLKIN_NUMBER - 1 + days) % 13 + 1,
        "haab_month": HAAB_MONTHS[haab // 20],
        "haab_day": haab % 20,
    }


def converter_expected(case_id: str) -> dict[str, str | int]:
    count, sign, number, month, day = CONVERTER_VALUES[case_id]
    return {
        "long_count": count,
        "tzolkin_sign": sign,
        "tzolkin_number": number,
        "haab_month": month,
        "haab_day": day,
    }


def pull() -> dict[str, Any]:
    day_counts = ["days_since_epoch", "julian_day_number"]
    converter_quantities = list(converter_expected("creation-era"))
    return {
        "format": 1,
        "domain": "mesoamerican-calendar",
        "sources": [
            {
                "name": "GMT correlation definition",
                "url": "https://en.wikipedia.org/wiki/Mesoamerican_Long_Count_calendar",
                "command": "python -m benchmark pull mesoamerican-calendar",
                "retrieved": "2026-10-09",
                "licence": "Calendar definition, facts only; the page is CC BY-SA",
                "method": (
                    "Recomputed from the definition: the epoch 13.0.0.0.0 = 4 Ajaw 8 Kumku sits "
                    "at Julian Day Number 584283, the day count is the Julian Day Number minus "
                    "584283, the Long Count is that count in base 20 with 18 winal to a tun, the "
                    "Tzolkin runs 13 numbers against 20 day signs and the Haab runs 18 months of "
                    "20 days plus the 5 days of Wayeb, both from the epoch. The Julian Day Number "
                    "of a proleptic Gregorian date follows Fliegel and Van Flandern."
                ),
                "citation": (
                    "Fliegel and Van Flandern, A machine algorithm for processing calendar "
                    "dates, Communications of the ACM 11 (10), 1968, p. 657"
                ),
                "notes": (
                    "Dates are proleptic Gregorian for every year. A converter that reads dates "
                    "before 15 October 1582 as Julian differs by ten or eleven days."
                ),
            },
            {
                "name": "FAMSI date converter",
                "url": "https://research.famsi.org/date_mayaLC.php",
                "retrieved": "2026-10-09",
                "licence": "Published tool output, values only",
                "method": (
                    "Gregorian date and correlation constant 584283 entered in the converter "
                    "form; the Long Count and Calendar Round it printed were transcribed. "
                    "The recomputation above is asserted to reproduce every value."
                ),
                "applies_to": converter_quantities,
            },
        ],
        "families": [
            {
                "label": "Long Count and day count",
                "quantities": ["long_count", "days_since_epoch", "julian_day_number"],
            },
            {"label": "Tzolkin sign and number", "quantities": ["tzolkin_sign", "tzolkin_number"]},
            {"label": "Haab month and day", "quantities": ["haab_month", "haab_day"]},
        ],
        "tolerances": [
            {
                "applies_to": day_counts,
                "value": 0,
                "unit": "days",
                "why": "A day count is an integer from a fixed epoch, any miss is a wrong day.",
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": "Long Count, Tzolkin and Haab values are discrete: a one day shift fails.",
            },
        ],
        "cases": [
            {
                "id": case_id,
                "input": {"date": iso_date, "correlation": CORRELATION_ID},
                "expected": quantities(iso_date),
            }
            for case_id, iso_date, _ in DATES
        ],
        "cross_checks": [
            {
                "id": case_id,
                "source": "FAMSI date converter",
                "input": {"date": iso_date, "correlation": CORRELATION_ID},
                "expected": converter_expected(case_id),
            }
            for case_id, iso_date, _ in DATES
        ],
    }
