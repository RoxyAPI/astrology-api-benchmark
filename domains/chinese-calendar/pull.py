"""Rebuild ``references.json`` from the Hong Kong Observatory tables and the sexagenary definition.

Solar term dates and lunar new year dates are read from the Observatory Gregorian-Lunar conversion
tables, one text file per year. The tables print calendar dates in Hong Kong Time, UTC+8, which is
the reference meridian the API reports its local dates at, so the two are compared like with like.
The tables give dates, not instants: the unit is days with no tolerance.

The four pillars are recomputed from the sexagenary definition. The day count is anchored on a
published jiazi day, the year cycle on the published rule that 4 CE is a jiazi year, the month stem
on the five tigers rule and the hour stem on the five rats rule. Month boundaries come from the
Observatory dates of the twelve jie terms, so a birth is always placed by a table that is not the
API. Run it with ``uv run python -m benchmark pull chinese-calendar``.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, date, datetime
from typing import Any

from benchmark.fetch import get_text

HKO_URL = "https://www.hko.gov.hk/en/gts/time/calendar/text/files/T{year}e.txt"

STEMS = ("jia", "yi", "bing", "ding", "wu", "ji", "geng", "xin", "ren", "gui")
BRANCHES = ("zi", "chou", "yin", "mao", "chen", "si", "wu", "wei", "shen", "you", "xu", "hai")

# Observatory term name to the API term id. Longitudes are the Observatory table, 0 degrees for the
# vernal equinox in steps of 15, so the order here is the order of the ecliptic.
HKO_TERMS: dict[str, str] = {
    "Vernal Equinox": "chun-fen",
    "Bright & Clear": "qing-ming",
    "Corn Rain": "gu-yu",
    "Summer Commences": "li-xia",
    "Corn Forms": "xiao-man",
    "Corn on Ear": "mang-zhong",
    "Summer Solstice": "xia-zhi",
    "Moderate Heat": "xiao-shu",
    "Great Heat": "da-shu",
    "Autumn Commences": "li-qiu",
    "End of Heat": "chu-shu",
    "White Dew": "bai-lu",
    "Autumnal Equinox": "qiu-fen",
    "Cold Dew": "han-lu",
    "Frost": "shuang-jiang",
    "Winter Commences": "li-dong",
    "Light Snow": "xiao-xue",
    "Heavy Snow": "da-xue",
    "Winter Solstice": "dong-zhi",
    "Moderate Cold": "xiao-han",
    "Severe Cold": "da-han",
    "Spring Commences": "li-chun",
    "Spring Showers": "yu-shui",
    "Insects Waken": "jing-zhe",
}

# The twelve jie terms in month order: the month of the yin branch opens at li-chun.
JIE_TERMS = (
    "li-chun", "jing-zhe", "qing-ming", "li-xia", "mang-zhong", "xiao-shu",
    "li-qiu", "bai-lu", "han-lu", "li-dong", "da-xue", "xiao-han",
)  # fmt: skip

SOLAR_TERM_YEARS = (1950, 1985, 2026, 2050)
LUNAR_NEW_YEAR_YEARS = (1920, 1950, 1985, 2000, 2026, 2050, 2099)

ANCHOR_DAY = date(1949, 10, 1)
"""A jiazi day, the first of the sexagenary day cycle."""
ANCHOR_YEAR = 4
"""A jiazi year, the first of the sexagenary year cycle."""
UTC_PLUS_8 = 8

# (case id, ISO date, local time, why the case is here). Times sit in the middle of a two hour
# branch and outside 23:00 to 00:59, where the day boundary schools differ. No date falls on a jie
# term date, where only an instant could place the month.
PILLAR_CHARTS = (
    ("spring-1950", "1950-03-15", "08:30:00", "a mid century birth in the mao month"),
    (
        "before-lichun",
        "2026-02-03",
        "12:00:00",
        "the day before Lichun: previous year and chou month",
    ),
    ("after-lichun", "2026-02-05", "12:00:00", "the day after Lichun: new year and yin month"),
    ("first-day-2000", "2000-01-01", "12:00:00", "January before Xiaohan: previous year, zi month"),
    ("after-xiaohan", "2025-01-10", "16:20:00", "January after Xiaohan: previous year, chou month"),
    ("winter-1976", "1976-11-20", "19:45:00", "a late autumn birth in the hai month"),
    ("year-end-1985", "1985-12-25", "14:10:00", "a December birth in the zi month"),
    ("autumn-2049", "2049-08-20", "21:15:00", "a future birth in the shen month"),
)


def pillar(index: int) -> str:
    """Pillar id of a sexagenary index 0 to 59, where 0 is jia-zi."""
    return f"{STEMS[index % 10]}-{BRANCHES[index % 12]}"


def year_pillar(solar_year: int) -> str:
    """Rule used by the sexagenary year cycle: 4 CE is jia-zi and the cycle repeats every 60."""
    return pillar((solar_year - ANCHOR_YEAR) % 60)


def day_pillar(day: date) -> str:
    return pillar((day.toordinal() - ANCHOR_DAY.toordinal()) % 60)


def month_pillar(year_stem: int, month_index: int) -> str:
    """Five tigers rule: the yin month takes the stem two places after twice the year stem.

    ``month_index`` counts from the yin month at 0, so the chou month that closes the year is 11.
    """
    stem = (2 * year_stem + 2 + month_index) % 10
    return f"{STEMS[stem]}-{BRANCHES[(2 + month_index) % 12]}"


def hour_pillar(day_stem: int, hour: int) -> str:
    """Five rats rule: the zi hour takes the stem twice the day stem, then one stem per branch."""
    branch = ((hour + 1) // 2) % 12
    return f"{STEMS[(2 * day_stem + branch) % 10]}-{BRANCHES[branch]}"


class Table:
    """One Observatory year: term dates by id, lunar new year and the header year pillar."""

    def __init__(self, year: int) -> None:
        url = HKO_URL.format(year=year)
        text = get_text(url, encoding="latin-1")
        header = re.search(rf"Table of {year} \(?(\w+)-(\w+)", text)
        if header is None:
            raise ValueError(f"{url}: no year header")
        self.year_pillar = f"{header[1].lower()}-{header[2].lower()}"
        self.terms: dict[str, date] = {}
        self.lunar_new_year: date | None = None
        for line in text.splitlines():
            cells = re.split(r"\s{2,}", line.strip())
            when = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", cells[0])
            if when is None or len(cells) < 3:
                continue
            day = date(int(when[1]), int(when[2]), int(when[3]))
            if cells[1].lower() == "1st lunar month" and self.lunar_new_year is None:
                self.lunar_new_year = day
            if len(cells) > 3:
                self.terms[HKO_TERMS[cells[3]]] = day
        if len(self.terms) != len(HKO_TERMS) or self.lunar_new_year is None:
            raise ValueError(f"{url}: expected 24 terms and a lunar new year")


class Tables:
    """Observatory tables fetched once per year."""

    def __init__(self) -> None:
        self._cache: dict[int, Table] = {}

    def __getitem__(self, year: int) -> Table:
        if year not in self._cache:
            print(f"fetching {HKO_URL.format(year=year)}", file=sys.stderr)
            self._cache[year] = Table(year)
        return self._cache[year]


def solar_terms(tables: Tables, year: int) -> dict[str, str]:
    """The 24 terms of a solar year: Li Chun to Dong Zhi in ``year``, the last two in January."""
    here, after = tables[year].terms, tables[year + 1].terms
    return {
        term: (after[term] if term in ("xiao-han", "da-han") else here[term]).isoformat()
        for term in sorted(HKO_TERMS.values(), key=lambda t: _term_order(tables, year, t))
    }


def _term_order(tables: Tables, year: int, term: str) -> date:
    january = term in ("xiao-han", "da-han")
    return tables[year + january].terms[term]


def pillars(tables: Tables, day: date, hour: int) -> dict[str, str]:
    """Year, month, day and hour pillars of a birth placed by the Observatory jie dates."""
    this_year = tables[day.year].terms
    if day == this_year["li-chun"]:
        raise ValueError(f"{day}: on the Li Chun date only an instant can place the year")
    solar_year = day.year if day > this_year["li-chun"] else day.year - 1
    boundaries = {
        tables[year].terms[term]: term for year in (day.year - 1, day.year) for term in JIE_TERMS
    }
    if day in boundaries:
        raise ValueError(f"{day}: on a jie date only an instant can place the month")
    term = boundaries[max(when for when in boundaries if when < day)]
    year = year_pillar(solar_year)
    stem = STEMS.index(year.split("-")[0])
    day_id = day_pillar(day)
    return {
        "year_pillar": year,
        "month_pillar": month_pillar(stem, JIE_TERMS.index(term)),
        "day_pillar": day_id,
        "hour_pillar": hour_pillar(STEMS.index(day_id.split("-")[0]), hour),
    }


def cross_checks(tables: Tables) -> list[dict[str, Any]]:
    """Values transcribed from published tables and worked examples, reproduced by the rules."""
    checks: list[dict[str, Any]] = []
    for source, day in (
        ("Sexagenary cycle", "1949-10-01"),
        ("Ganzhi", "1912-02-18"),
    ):
        checks.append(_check(f"day-{day}", source, {"date": day}, {"day_pillar": "jia-zi"}))
    checks.append(
        _check(
            "year-1984",
            "Sexagenary cycle",
            {"solar_year": 1984},
            {"year_pillar": "jia-zi"},
        )
    )
    for year in (1950, 2026, 2050):
        checks.append(
            _check(
                f"year-{year}-observatory",
                "Hong Kong Observatory Gregorian-Lunar calendar conversion table",
                {"solar_year": year, "reading": "table header, a mid year date"},
                {"year_pillar": tables[year].year_pillar},
            )
        )
    for year_stem, yin, zi in MONTH_TABLE:
        for label, index, expected in (("yin", 0, yin), ("zi", 10, zi)):
            checks.append(
                _check(
                    f"month-{label}-{year_stem}-year",
                    "Sexagenary cycle",
                    {"year_stem": year_stem, "month_index": index},
                    {"month_pillar": expected},
                )
            )
    for day_stem, zi_hour in HOUR_TABLE:
        checks.append(
            _check(
                f"hour-zi-{day_stem}-day",
                "Sexagenary cycle",
                {"day_stem": day_stem, "hour": 0},
                {"hour_pillar": zi_hour},
            )
        )
    return checks


# English Wikipedia "Sexagenary cycle": names of the yin and zi months by year stem group, and the
# zi hour by day stem group. The jia, ji and companion stems in each group share a row.
MONTH_TABLE = (
    ("jia", "bing-yin", "bing-zi"),
    ("yi", "wu-yin", "wu-zi"),
    ("bing", "geng-yin", "geng-zi"),
    ("ding", "ren-yin", "ren-zi"),
    ("wu", "jia-yin", "jia-zi"),
)
HOUR_TABLE = (
    ("jia", "jia-zi"),
    ("yi", "bing-zi"),
    ("bing", "wu-zi"),
    ("ding", "geng-zi"),
    ("wu", "ren-zi"),
)


def _check(
    check_id: str, source: str, given: dict[str, Any], expected: dict[str, str]
) -> dict[str, Any]:
    return {"id": check_id, "source": source, "input": given, "expected": expected}


def pull() -> dict[str, Any]:
    tables = Tables()
    cases: list[dict[str, Any]] = [
        {
            "id": f"solar-terms-{year}",
            "input": {"year": year},
            "expected": solar_terms(tables, year),
        }
        for year in SOLAR_TERM_YEARS
    ]
    cases += [
        {
            "id": f"lunar-new-year-{year}",
            "input": {"lunarYear": year, "lunarMonth": 1, "lunarDay": 1},
            "expected": {"lunar_new_year": tables[year].lunar_new_year.isoformat()},  # type: ignore[union-attr]
        }
        for year in LUNAR_NEW_YEAR_YEARS
    ]
    for case_id, iso_day, clock, _ in PILLAR_CHARTS:
        day = date.fromisoformat(iso_day)
        cases.append(
            {
                "id": f"pillars-{case_id}",
                "input": {"date": iso_day, "time": clock, "timezone": UTC_PLUS_8},
                "expected": pillars(tables, day, int(clock[:2])),
            }
        )
    retrieved = datetime.now(UTC).date().isoformat()
    quantities = list(dict.fromkeys(q for c in cases for q in c["expected"]))
    return {
        "format": 1,
        "domain": "chinese-calendar",
        "sources": [
            {
                "name": "Hong Kong Observatory Gregorian-Lunar calendar conversion table",
                "url": "https://www.hko.gov.hk/en/gts/time/conversion.htm",
                "command": "python -m benchmark pull chinese-calendar (one text file per year)",
                "retrieved": retrieved,
                "licence": (
                    "Hong Kong Government open data: free to reproduce for commercial and "
                    "non-commercial use with attribution to the Government and DATA.GOV.HK"
                ),
                "method": (
                    "The text file of each year lists every date with its lunar date and, on "
                    "term days, the solar term. Term dates are the calendar dates in Hong Kong "
                    "Time, UTC+8; the first day of the first lunar month is the lunar new year. "
                    "Month pillars are placed by the dates of the twelve jie terms."
                ),
                "notes": (
                    "The tables publish dates, so the unit is days. The Observatory states that "
                    "an event close to midnight can differ by one day for decades ahead; the "
                    "listed years avoid its named cases. Each file header also names the year "
                    "pillar of the lunar year."
                ),
                "applies_to": [
                    *sorted(HKO_TERMS.values()),
                    "lunar_new_year",
                    "year_pillar",
                    "month_pillar",
                ],
            },
            {
                "name": "Sexagenary cycle",
                "url": "https://en.wikipedia.org/wiki/Sexagenary_cycle",
                "retrieved": retrieved,
                "licence": "Calendar definition, facts only; the page is CC BY-SA",
                "method": (
                    "Day pillar by days since the jiazi day 1 October 1949, the worked example "
                    "of the page. Year pillar by the rule that 4 CE is a jiazi year, applied to "
                    "the solar year that opens at Li Chun. Month stem by the five tigers rule "
                    "and hour stem by the five rats rule, both checked against the page tables "
                    "of month and hour names. Dates are proleptic Gregorian."
                ),
                "applies_to": ["day_pillar", "hour_pillar", "year_pillar", "month_pillar"],
            },
            {
                "name": "Ganzhi",
                "url": "https://zh.wikipedia.org/wiki/干支",
                "retrieved": retrieved,
                "licence": "Calendar definition, facts only; the page is CC BY-SA",
                "method": (
                    "The worked example of the page for 18 February 1912, a jiazi day, "
                    "transcribed and reproduced by the day count above."
                ),
                "applies_to": ["day_pillar"],
            },
        ],
        "families": [
            {
                "label": "Solar terms and Lunar New Year",
                "quantities": [q for q in quantities if "-" in q or q == "lunar_new_year"],
            },
            {
                "label": "Four pillars",
                "quantities": [q for q in quantities if q.endswith("_pillar")],
            },
        ],
        "tolerances": [
            {
                "applies_to": ["year_pillar", "month_pillar", "day_pillar", "hour_pillar"],
                "value": 0,
                "unit": "exact",
                "why": "A pillar is a discrete stem and branch pair: any miss is a wrong pillar.",
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "days",
                "why": (
                    "The tables publish calendar dates, not instants, so a date either matches "
                    "or is a whole day away."
                ),
            },
        ],
        "cases": cases,
        "cross_checks": cross_checks(tables),
    }
