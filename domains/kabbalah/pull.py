"""Rebuild ``references.json`` from published definitions, with no network access.

Gematria: Mispar Hechrachi gives the 22 letters the values 1 to 9, 10 to 90 and 100 to 400, and the
five word final forms count as the regular letter they are a form of. Mispar Gadol continues the
sequence with the final forms at 500 to 900. Both are summed from the letter table below, after
removing the vowel points, cantillation marks and punctuation that carry no value.

Hebrew calendar: the arithmetic calendar of Dershowitz and Reingold, Calendrical Calculations,
chapter 8 (The Hebrew Calendar), in the Rata Die day count where Gregorian 0001-01-01 is day 1. The
Hebrew day begins at sunset. A civil date taken as the whole day from midnight to midnight is
dated by this function directly; a moment after nightfall belongs to the next date, which is the
same function applied to the following civil day.

The second source for each part was transcribed by hand into ``WORKED_EXAMPLES`` and
``CONVERTER_DATES`` below, and a test asserts the recomputation reproduces every value.
"""

# ruff: noqa: RUF001
# The Hebrew letters below are the data, not look-alike typos.
from __future__ import annotations

import unicodedata
from datetime import date, timedelta
from typing import Any

HECHRACHI = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ל": 30, "מ": 40, "נ": 50, "ס": 60, "ע": 70, "פ": 80, "צ": 90,
    "ק": 100, "ר": 200, "ש": 300, "ת": 400,
}  # fmt: skip
"""The 22 letters and their standard values."""

FINAL_FORMS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
"""Each word final form and the regular letter it is a form of."""

GADOL_FINALS = {"ך": 500, "ם": 600, "ן": 700, "ף": 800, "ץ": 900}
"""Mispar Gadol values for the five final forms."""

# (case id, Hebrew text, why the case is here)
WORDS = (
    ("shalom", "שלום", "a final mem: 40 in Mispar Hechrachi, 600 in Mispar Gadol"),
    ("wine", "יין", "a final nun, the worked example in the Talmud passage on wine and secret"),
    ("secret", "סוד", "the word of equal value in the same passage, no final form"),
    ("life", "חי", "the two letter word whose value 18 is widely cited"),
    ("truth", "אֶמֶת", "written with vowel points, which carry no value"),
    ("king", "מלך", "a final kaf, 20 in Mispar Hechrachi, 500 in Mispar Gadol"),
    ("land", "ארץ", "a final tsadi, 90 in Mispar Hechrachi, 900 in Mispar Gadol"),
    ("the-adversary", "השטן", "a four letter word ending in a final nun, value 364"),
    ("mouth", "פה", "a pe in the middle of the word, the regular form"),
    ("final-pe", "כף", "a final pe, 80 in Mispar Hechrachi, 800 in Mispar Gadol"),
)

# word -> value printed by the cited source, sum under the regular letter values
WORKED_EXAMPLES: dict[str, int] = {
    "יין": 70,
    "סוד": 70,
    "חי": 18,
    "אמת": 441,
    "השטן": 364,
    "אליעזר": 318,
}
"""Gematria sums printed in the Wikipedia article Gematria, with their Talmud and Midrash cites."""

HEBREW_EPOCH = -1_373_427
"""Rata Die of 1 Tishri of Hebrew year 1, the Julian date 7 October 3761 BCE."""

TISHRI = 7

# (case id, ISO date, after sunset, why the case is here)
DATES = (
    ("rosh-hashanah-5786", "2025-09-23", False, "1 Tishri 5786, the Hebrew new year"),
    ("eve-of-rosh-hashanah", "2025-09-22", False, "29 Elul 5785, the last day of the year"),
    ("after-sunset-eve", "2025-09-22", True, "the evening after sunset, already 1 Tishri 5786"),
    ("rosh-hashanah-5787", "2026-09-12", False, "1 Tishri 5787, the opening of a leap year"),
    ("shevat-end", "2024-02-09", False, "30 Shevat in a leap year, the last day before Adar I"),
    ("adar-i-start", "2024-02-10", False, "1 Adar I 5784, the first day of the extra month"),
    ("adar-i-end", "2024-03-10", False, "30 Adar I, the last day of the leap month"),
    ("adar-ii-start", "2024-03-11", False, "1 Adar II 5784, month number 13"),
    ("nisan-start", "2024-04-09", False, "1 Nisan 5784, the month the year count is anchored to"),
    ("plain-adar", "2025-03-10", False, "10 Adar in a year without a second Adar"),
    ("mid-year", "1990-06-15", False, "22 Sivan 5750, a mid year date"),
    ("early-modern", "1700-01-01", False, "a date in the eighteenth century"),
    ("year-before-reform", "1582-10-04", False, "the day before the reform, read proleptically"),
)  # fmt: skip

CONVERTER_DATES: dict[tuple[str, bool], tuple[int, int, int]] = {
    ("2025-09-23", False): (5786, 7, 1),
    ("2025-09-22", False): (5785, 6, 29),
    ("2025-09-22", True): (5786, 7, 1),
    ("2026-09-12", False): (5787, 7, 1),
    ("2024-02-09", False): (5784, 11, 30),
    ("2024-02-10", False): (5784, 12, 1),
    ("2024-03-10", False): (5784, 12, 30),
    ("2024-03-11", False): (5784, 13, 1),
    ("2024-04-09", False): (5784, 1, 1),
    ("1990-06-15", False): (5750, 3, 22),
    ("2025-03-10", False): (5785, 12, 10),
    ("1700-01-01", False): (5460, 10, 10),
}
"""Hebrew year, month number (Nisan 1, Tishri 7, Adar II 13) and day as the published converter
printed them for the Gregorian date, from its month names."""


def letters(text: str) -> list[str]:
    """The Hebrew letters of a string, with points, cantillation and punctuation removed."""
    return [c for c in unicodedata.normalize("NFC", text) if "א" <= c <= "ת"]


def mispar_hechrachi(text: str) -> int:
    """Standard value: final forms count as their regular letter."""
    return sum(HECHRACHI[FINAL_FORMS.get(c, c)] for c in letters(text))


def mispar_gadol(text: str) -> int:
    """Large value: the final forms continue the sequence at 500 to 900."""
    return sum(GADOL_FINALS.get(c, HECHRACHI.get(c, 0)) for c in letters(text))


def leap_year(year: int) -> bool:
    """Seven years in each cycle of nineteen carry a second Adar (Calendrical Calculations 8.1)."""
    return (7 * year + 1) % 19 < 7


def last_month(year: int) -> int:
    return 13 if leap_year(year) else 12


def elapsed_days(year: int) -> int:
    """Days from the epoch to the molad of Tishri, postponed by the first dehiyyah rule."""
    months = (235 * year - 234) // 19
    parts = 12084 + 13753 * months
    days = 29 * months + parts // 25920
    return days + 1 if (3 * (days + 1)) % 7 < 3 else days


def year_length_correction(year: int) -> int:
    """The second and third dehiyyah rules, which keep a year from 356 or 382 days."""
    ny0, ny1, ny2 = elapsed_days(year - 1), elapsed_days(year), elapsed_days(year + 1)
    if ny2 - ny1 == 356:
        return 2
    return 1 if ny1 - ny0 == 382 else 0


def new_year(year: int) -> int:
    """Rata Die of 1 Tishri."""
    return HEBREW_EPOCH + elapsed_days(year) + year_length_correction(year)


def days_in_year(year: int) -> int:
    return new_year(year + 1) - new_year(year)


def month_length(year: int, month: int) -> int:
    """Days in a month; Cheshvan and Kislev vary with the length of the year."""
    if month in (2, 4, 6, 10, 13) or (month == 12 and not leap_year(year)):
        return 29
    if month == 8 and days_in_year(year) not in (355, 385):
        return 29
    if month == 9 and days_in_year(year) in (353, 383):
        return 29
    return 30


def fixed_from_hebrew(year: int, month: int, day: int) -> int:
    """Rata Die of a Hebrew date; months run from Tishri to the last Adar, then Nisan to Elul."""
    if month < TISHRI:
        before = list(range(TISHRI, last_month(year) + 1)) + list(range(1, month))
    else:
        before = list(range(TISHRI, month))
    return new_year(year) + day - 1 + sum(month_length(year, m) for m in before)


def hebrew_from_fixed(rata_die: int) -> tuple[int, int, int]:
    """Hebrew year, month number and day of a Rata Die."""
    year = (rata_die - HEBREW_EPOCH) * 98496 // 35975351 - 1
    while new_year(year + 1) <= rata_die:
        year += 1
    month = TISHRI if rata_die < fixed_from_hebrew(year, 1, 1) else 1
    while rata_die > fixed_from_hebrew(year, month, month_length(year, month)):
        month += 1
    return year, month, rata_die - fixed_from_hebrew(year, month, 1) + 1


def hebrew_date(iso_date: str, after_sunset: bool = False) -> dict[str, Any]:
    """Quantities for a proleptic Gregorian date, advanced one day when it is after sunset."""
    civil = date.fromisoformat(iso_date)
    if after_sunset:
        civil += timedelta(days=1)
    year, month, day = hebrew_from_fixed(civil.toordinal())
    return {"hebrew_year": year, "month_number": month, "day": day, "leap_year": leap_year(year)}


def pull() -> dict[str, Any]:
    gematria_quantities = ["mispar_hechrachi", "mispar_gadol"]
    calendar_quantities = ["hebrew_year", "month_number", "day", "leap_year"]
    return {
        "format": 1,
        "domain": "kabbalah",
        "sources": [
            {
                "name": "Mispar Hechrachi letter table",
                "url": "https://en.wikipedia.org/wiki/Gematria",
                "command": "python -m benchmark pull kabbalah",
                "retrieved": "2026-10-09",
                "licence": "Letter values, facts only; the page is CC BY-SA",
                "method": (
                    "Recomputed from the published letter table: the 22 letters carry 1 to 9, "
                    "10 to 90 and 100 to 400, and the five final forms count as the regular "
                    "letter they are a form of, which is Mispar Hechrachi. Mispar Gadol "
                    "continues the sequence with the final forms at 500 to 900. Vowel points "
                    "and cantillation marks carry no value and are removed first."
                ),
                "applies_to": gematria_quantities,
                "notes": (
                    "Final letters in Mispar Hechrachi take the regular value: the page states "
                    "that the final forms are given their own values from 500 to 900 only in "
                    "Mispar Gadol."
                ),
            },
            {
                "name": "Dershowitz and Reingold, Calendrical Calculations",
                "url": "https://www.cambridge.org/core/books/calendrical-calculations/B897CA3260110348F1F7D906B8D9480D",
                "citation": (
                    "Dershowitz and Reingold, Calendrical Calculations, Cambridge University "
                    "Press, chapter 8 The Hebrew Calendar"
                ),
                "retrieved": "2026-10-09",
                "licence": "Published algorithm, recomputed; no text or code copied",
                "method": (
                    "The arithmetic Hebrew calendar: leap years by (7y + 1) mod 19 < 7, the "
                    "molad of Tishri from the mean lunation 29 days 12 hours 793 parts, the "
                    "four postponement rules, and month lengths set by the year length. The "
                    "Hebrew day begins at sunset, so a civil date from midnight is dated "
                    "directly and a moment after nightfall takes the next civil date."
                ),
                "applies_to": calendar_quantities,
                "notes": "Dates are proleptic Gregorian for every year.",
            },
            {
                "name": "Hebcal date converter",
                "url": "https://www.hebcal.com/converter",
                "retrieved": "2026-10-09",
                "licence": "Published tool output, values only",
                "method": (
                    "The Gregorian date, with the after sunset option where noted, entered in "
                    "the converter; the Hebrew year, month and day it printed were transcribed. "
                    "The recomputation above is asserted to reproduce every value."
                ),
                "applies_to": calendar_quantities,
            },
        ],
        "families": [
            {
                "label": "Mispar Hechrachi and Mispar Gadol word values",
                "quantities": gematria_quantities,
            },
            {
                "label": "Hebrew year, month and day, with the leap year flag",
                "quantities": calendar_quantities,
            },
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": (
                    "A word value is a sum of integers and a calendar date is a discrete day "
                    "count, so one letter or one day off is a wrong answer."
                ),
            }
        ],
        "cases": [
            {
                "id": case_id,
                "input": {"gematria": {"textHebrew": word, "includeMatches": False}},
                "expected": {
                    "mispar_hechrachi": mispar_hechrachi(word),
                    "mispar_gadol": mispar_gadol(word),
                },
            }
            for case_id, word, _ in WORDS
        ]
        + [
            {
                "id": case_id,
                "input": {
                    "birth": {"date": iso_date, "timezone": "UTC", "afterSunset": after_sunset}
                },
                "expected": hebrew_date(iso_date, after_sunset),
            }
            for case_id, iso_date, after_sunset, _ in DATES
        ],
        "cross_checks": [
            {
                "id": word,
                "source": "Mispar Hechrachi letter table",
                "input": {"textHebrew": word},
                "expected": {"mispar_hechrachi": value},
            }
            for word, value in WORKED_EXAMPLES.items()
        ]
        + [
            {
                "id": f"{iso_date}{'-after-sunset' if after_sunset else ''}",
                "source": "Hebcal date converter",
                "input": {"date": iso_date, "afterSunset": after_sunset},
                "expected": {"hebrew_year": y, "month_number": m, "day": d},
            }
            for (iso_date, after_sunset), (y, m, d) in CONVERTER_DATES.items()
        ],
    }
