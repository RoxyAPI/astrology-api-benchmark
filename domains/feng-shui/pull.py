"""Rebuild ``references.json`` from the printed Qing rules and the Hong Kong Observatory tables.

Every star and Kua number here is recomputed from rules stated in printed texts, never read from
a chart caster:

* The Kua (the gua of a birth year in the Eight Mansions school) by the male and female nine
  palace rule of the imperial almanac: a man counts backwards from Kan 1, Xun 4 and Dui 7 at the
  jiazi years that open the upper, middle and lower eras, a woman forwards from 5, Kun 2 and
  Gen 8. A raw 5 has no trigram and lodges at Kun 2 for a man and Gen 8 for a woman.
* The annual centre star by the three era rule of the same almanac: 1, 4 and 7 enter the centre
  at the three jiazi years, one star back each year. The plate flies forward from the centre
  along the Lo Shu path the almanac spells out for the first year of the upper era.
* The natal chart of a building by the Xuan Kong rules of the Shen school: the period star
  enters the centre and flies forward; the stars that land on the sitting and the facing palace
  enter the centre as the mountain and the water star and fly forward when the mountain of the
  same position in the home palace of that star is yang, in reverse when it is yin. A 5 takes the
  polarity of the sitting or facing mountain itself.

The upper era opened in the jiazi year 1864: the almanac counts eras from 1684 and its earlier
source from 1504, each 180 years before the next, and the Xuan Kong text names 1864 directly.
The solar year turns at Li Chun. Its date in each year is read from the Observatory tables in
Hong Kong Time, UTC+8, where the API reads a date-only input at the start of the day. Run it with
``uv run python -m benchmark pull feng-shui``.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, date, datetime
from typing import Any

from benchmark.fetch import get_text

HKO_URL = "https://www.hko.gov.hk/en/gts/time/calendar/text/files/T{year}e.txt"

CYCLE_START = 1864
"""Jiazi year that opened the upper era; eras run 60 years and the cycle 180."""
ERAS = ("upper", "middle", "lower")
MALE_START = (1, 4, 7)
FEMALE_START = (5, 2, 8)
MALE_LODGE, FEMALE_LODGE = 2, 8

PALACES = (
    "Center", "Northwest", "West", "Northeast", "South", "North", "Southwest", "East", "Southeast",
)  # fmt: skip
"""Lo Shu flight path: a plate entering the centre flies to the palaces in this order."""
HOME = {1: "North", 2: "Southwest", 3: "East", 4: "Southeast", 6: "Northwest", 7: "West"}
HOME |= {8: "Northeast", 9: "South"}
"""Palace of each star on the Lo Shu base plate, where 5 sits in the centre."""

MOUNTAINS = (
    "ren", "zi", "gui", "chou", "gen", "yin", "jia", "mao", "yi", "chen", "xun", "si",
    "bing", "wu", "ding", "wei", "kun", "shen", "geng", "you", "xin", "xu", "qian", "hai",
)  # fmt: skip
"""The 24 mountains clockwise from north, three to a palace: earth, heaven and human dragon."""
MOUNTAIN_PALACE = (
    "North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest",
)  # fmt: skip
"""Palace of each run of three mountains, in the same clockwise order."""

STEMS = ("jia", "yi", "bing", "ding", "wu", "ji", "geng", "xin", "ren", "gui")
BRANCHES = ("zi", "chou", "yin", "mao", "chen", "si", "wu", "wei", "shen", "you", "xu", "hai")

# (case id, date, gender, why the case is here)
KUA_CASES = (
    ("before-lichun-2026-male", "2026-02-03", "male", "the day before Li Chun: solar year 2025"),
    ("lichun-day-2026-female", "2026-02-04", "female", "the Li Chun day: the outgoing year"),
    ("after-lichun-2026-female", "2026-02-05", "female", "a raw 5 for a woman lodges at 8"),
    ("after-lichun-2026-male", "2026-02-05", "male", "the day after Li Chun: solar year 2026"),
    ("early-lichun-2025-male", "2025-02-04", "male", "Li Chun fell on 3 February: new year"),
    ("raw-five-1986-male", "1986-06-15", "male", "a raw 5 for a man lodges at 2"),
    ("before-lichun-1950-female", "1950-01-20", "female", "a January birth: solar year 1949"),
    ("century-2100-male", "2100-06-15", "male", "a century year where digit sum tables slip"),
)
ANNUAL_YEARS = (1901, 1984, 2024, 2026, 2100)
# (period, facing mountain, why the chart is here)
NATAL_CHARTS = (
    (8, "wu", "both prosperous stars meet at the facing, mountain forward, water reverse"),
    (9, "zi", "a 5 enters the centre on the water plate and takes the facing polarity, yin"),
    (4, "xun", "a 5 enters the centre on the mountain plate and takes the sitting polarity"),
    (6, "you", "both plates fly forward"),
    (5, "ding", "the period 5 plate, both plates in reverse, a human dragon facing"),
    (1, "bing", "an earth dragon facing with a 5 on the water plate flying forward"),
)


def era_count(year: int, starts: tuple[int, int, int], step: int) -> int:
    """Nine palace count of a solar year: the era start, then ``step`` palaces a year, in 1 to 9."""
    offset = (year - CYCLE_START) % 180
    return (starts[offset // 60] - 1 + step * (offset % 60)) % 9 + 1


def raw_kua(year: int, gender: str) -> int:
    if gender == "male":
        return era_count(year, MALE_START, -1)
    return era_count(year, FEMALE_START, 1)


def kua(year: int, gender: str) -> int:
    raw = raw_kua(year, gender)
    if raw != 5:
        return raw
    return MALE_LODGE if gender == "male" else FEMALE_LODGE


def annual_star(year: int) -> int:
    """Centre star of a solar year: 1, 4 and 7 at the three jiazi years, one back each year."""
    return era_count(year, MALE_START, -1)


def fly(centre: int, forward: bool = True) -> dict[str, int]:
    """Plate of a star entering the centre: every palace along the path, forward or reverse."""
    step = 1 if forward else -1
    return {palace: (centre - 1 + step * k) % 9 + 1 for k, palace in enumerate(PALACES)}


def is_yang(mountain: str) -> bool:
    """Xuan Kong polarity: in the four cardinal palaces the earth dragon is yang and the heaven
    and human dragons yin; in the four corner palaces the reverse."""
    index = MOUNTAINS.index(mountain)
    cardinal = (index // 3) % 2 == 0
    earth = index % 3 == 0
    return earth if cardinal else not earth


def mountain_of(palace: str, dragon: int) -> str:
    """Mountain at position ``dragon`` (0 earth, 1 heaven, 2 human) of a palace."""
    return MOUNTAINS[3 * MOUNTAIN_PALACE.index(palace) + dragon]


def palace_of(mountain: str) -> str:
    return MOUNTAIN_PALACE[MOUNTAINS.index(mountain) // 3]


def sitting(facing: str) -> str:
    return MOUNTAINS[(MOUNTAINS.index(facing) + 12) % 24]


def natal(period: int, facing: str) -> dict[str, Any]:
    """Period, mountain and water plates of a building, with the direction of each flight."""
    base = fly(period)
    plates: dict[str, Any] = {"period": base}
    for plate, mountain in (("mountain", sitting(facing)), ("water", facing)):
        star = base[palace_of(mountain)]
        dragon = MOUNTAINS.index(mountain) % 3
        forward = is_yang(mountain if star == 5 else mountain_of(HOME[star], dragon))
        plates[plate] = fly(star, forward)
        plates[f"{plate}_flight"] = "forward" if forward else "reverse"
    return plates


def natal_expected(period: int, facing: str) -> dict[str, Any]:
    chart = natal(period, facing)
    expected: dict[str, Any] = {}
    for plate in ("period", "mountain", "water"):
        expected |= {f"{plate}_{p.lower()}": star for p, star in chart[plate].items()}
    return expected | {f: chart[f] for f in ("mountain_flight", "water_flight")}


def lichun(year: int) -> date:
    """Calendar date of Li Chun in Hong Kong Time, from the Observatory table of ``year``."""
    url = HKO_URL.format(year=year)
    print(f"fetching {url}", file=sys.stderr)
    for line in get_text(url, encoding="latin-1").splitlines():
        if "Spring Commences" in line:
            y, m, d = re.match(r"\s*(\d{4})/(\d{1,2})/(\d{1,2})", line).groups()  # type: ignore[union-attr]
            return date(int(y), int(m), int(d))
    raise ValueError(f"{url}: no Spring Commences line")


def solar_year(day: date, boundary: date) -> int:
    """A date on or before the Li Chun day belongs to the outgoing year: the date is read at the
    start of its day and the Li Chun instant falls later that day."""
    return day.year if day > boundary else day.year - 1


def pillar(year: int) -> str:
    return f"{STEMS[(year - 4) % 10]}-{BRANCHES[(year - 4) % 12]}"


# Gujin Tushu Jicheng, the Yangzhai Shishu table of the gua of each birth year: Lo Shu number of
# the gua printed for a man and for a woman, in sexagenary order from jia-zi, per era. A man on a
# 5 year is printed lodging at Kun and a woman at Gen, so no digit is 5.
GUJIN_TABLE = {
    "upper": (
        "198762432198762432198762432198762432198762432198762432198762",
        "867891234867891234867891234867891234867891234867891234867891",
    ),
    "middle": (
        "432198762432198762432198762432198762432198762432198762432198",
        "234867891234867891234867891234867891234867891234867891234867",
    ),
    "lower": (
        "762432198762432198762432198762432198762432198762432198762432",
        "891234867891234867891234867891234867891234867891234867891234",
    ),
}

# Xieji Bianfang Shu, juan 8, the table of the year star entering the centre: the stars of the
# upper, middle and lower era, then the year pillars that take them.
XIEJI_YEAR_STARS = (
    ((1, 4, 7), "jia-zi gui-you ren-wu xin-mao geng-zi ji-you wu-wu"),
    ((9, 3, 6), "yi-chou jia-xu gui-wei ren-chen xin-chou geng-xu ji-wei"),
    ((8, 2, 5), "bing-yin yi-hai jia-shen gui-si ren-yin xin-hai geng-shen"),
    ((7, 1, 4), "ding-mao bing-zi yi-you jia-wu gui-mao ren-zi xin-you"),
    ((6, 9, 3), "wu-chen ding-chou bing-xu yi-wei jia-chen gui-chou ren-xu"),
    ((5, 8, 2), "ji-si wu-yin ding-hai bing-shen yi-si jia-yin gui-hai"),
    ((4, 7, 1), "geng-wu ji-mao wu-zi ding-you bing-wu yi-mao"),
    ((3, 6, 9), "xin-wei geng-chen ji-chou wu-xu ding-wei bing-chen"),
    ((2, 5, 8), "ren-shen xin-si geng-yin ji-hai wu-shen ding-si"),
)
# Xieji Bianfang Shu, juan 8, the worked plate of the jiazi year 1684 that opened an upper era.
XIEJI_1684_PLATE = {
    "Center": 1, "Northwest": 2, "West": 3, "Northeast": 4, "South": 5,
    "North": 6, "Southwest": 7, "East": 8, "Southeast": 9,
}  # fmt: skip

# Shen Shi Xuan Kong Xue, juan 4, the nine period table of every sitting mountain: per period 1
# to 9, the star that lands on the sitting palace, the star that lands on the facing palace, and
# how the mountain plate and the water plate fly (F forward, R reverse), as printed.
SHEN_TABLE = {
    "zi": "65FR 76RF 87FR 98RF 19RR 21FR 32RF 43FR 54RF",
    "wu": "56RF 67FR 78RF 89FR 91RR 12RF 23FR 34RF 45FR",
    "mao": "83FR 94RF 15RR 26RR 37RR 48FF 59RR 61FR 72RF",
    "you": "38RR 49FR 51RR 62FF 73RR 84FF 95RR 16RF 27FR",
    "qian": "29FR 31RR 42FF 53FR 64FF 75RF 86FF 97RR 18RF",
    "xun": "92RF 13RR 24FF 35RF 46FF 57FF 68FF 79RR 81FR",
    "gen": "47FR 58FF 69FR 71RR 82FF 93RR 14RF 25FF 36RF",
    "kun": "74RF 85FF 96RF 17RR 28FF 39RR 41FR 52FF 63FR",
    "yin": "47FR 58FF 69FR 71RR 82FF 93RR 14RF 25FF 36RF",
    "shen": "74RF 85FF 96RF 17RR 28FF 39RR 41FR 52FF 63FR",
    "si": "92RF 13RR 24FF 35RF 46FF 57FR 68FF 79RR 81FR",
    "hai": "29FR 31RR 42FF 53FR 64FF 75RF 86FF 97RR 18RF",
    "yi": "83FR 94RF 15RR 26FF 37RR 48FF 59RR 61FR 72RF",
    "xin": "38RF 49FR 51RR 62FF 73RR 84FF 95RR 16RF 27FR",
    "ding": "56RF 67FR 78RF 89FR 91RR 12RF 23FR 34RF 45FR",
    "gui": "65FR 76RF 87FR 98RF 19RR 21FR 32RF 43FR 54RF",
    "chen": "92FR 13FF 24RR 35FR 46RR 57RF 68RR 79FF 81RF",
    "xu": "29RF 31FF 42RR 53RF 64RR 75FR 86RR 97FF 18FR",
    "chou": "47RF 58RR 69RF 71FF 82RR 93FF 14FR 25RR 36FR",
    "wei": "74FR 85RR 96FR 17FF 28RR 39FF 41RF 52RR 63RF",
    "jia": "83RF 94FR 15FF 26RR 37FF 48RR 59FF 61RF 72FR",
    "geng": "38FR 49RF 51FF 62RR 73FF 84RR 95FF 16FR 27RF",
    "ren": "65RF 76FR 87RF 98FR 19FF 21RF 32FR 43RF 54FR",
    "bing": "56FR 67RF 78FR 89RF 91FF 12FR 23RF 34FR 45RF",
}
SHEN_ERRATA = {("mao", 4), ("you", 1), ("xun", 6)}
"""Rows whose printed flight contradicts the verdict printed on the same row (a both forward
chart called mountain up and water down only when both fly forward, and so on); left out."""


def cross_checks() -> list[dict[str, Any]]:
    """Values transcribed from the three printed tables, reproduced by the rules above."""
    checks: list[dict[str, Any]] = []
    for era_index, era in enumerate(ERAS):
        for gender, digits in zip(("male", "female"), GUJIN_TABLE[era], strict=True):
            for index, digit in enumerate(digits):
                year = CYCLE_START + 60 * era_index + index
                checks.append(
                    {
                        "id": f"kua-{era}-{pillar(year)}-{gender}",
                        "source": "Gujin Tushu Jicheng, Yangzhai Shishu",
                        "input": {
                            "era": era,
                            "year_pillar": pillar(year),
                            "solar_year": year,
                            "gender": gender,
                        },
                        "expected": {"kua": int(digit)},
                    }
                )
    for stars, pillars in XIEJI_YEAR_STARS:
        for era_index, era in enumerate(ERAS):
            checks.append(
                {
                    "id": f"year-star-{era}-{pillars.split()[0]}",
                    "source": "Xieji Bianfang Shu",
                    "input": {"era": era, "year_pillars": pillars.split()},
                    "expected": {"annual_center": stars[era_index]},
                }
            )
    checks.append(
        {
            "id": "annual-plate-1684",
            "source": "Xieji Bianfang Shu",
            "input": {"solar_year": 1684},
            "expected": {f"annual_{p.lower()}": s for p, s in XIEJI_1684_PLATE.items()},
        }
    )
    for mountain, row in SHEN_TABLE.items():
        for period, code in enumerate(row.split(), start=1):
            if (mountain, period) in SHEN_ERRATA:
                continue
            checks.append(
                {
                    "id": f"natal-{mountain}-sitting-period-{period}",
                    "source": "Shen Shi Xuan Kong Xue",
                    "input": {"period": period, "facing": sitting(mountain)},
                    "expected": {
                        "mountain_center": int(code[0]),
                        "water_center": int(code[1]),
                        "mountain_flight": "forward" if code[2] == "F" else "reverse",
                        "water_flight": "forward" if code[3] == "F" else "reverse",
                    },
                }
            )
    return checks


def pull() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case_id, iso_day, gender, _ in KUA_CASES:
        day = date.fromisoformat(iso_day)
        boundary = lichun(day.year)
        year = solar_year(day, boundary)
        cases.append(
            {
                "id": f"kua-{case_id}",
                "input": {"date": iso_day, "gender": gender, "yearBoundary": "li-chun"},
                "expected": {
                    "kua": kua(year, gender),
                    "raw_kua": raw_kua(year, gender),
                    "solar_year": year,
                    "boundary_date": boundary.isoformat(),
                },
            }
        )
    for year in ANNUAL_YEARS:
        plate = {f"annual_{p.lower()}": s for p, s in fly(annual_star(year)).items()}
        cases.append(
            {
                "id": f"annual-{year}",
                "input": {"year": year},
                "expected": plate | {"changeover_date": lichun(year).isoformat()},
            }
        )
    for period, facing, _ in NATAL_CHARTS:
        cases.append(
            {
                "id": f"natal-period-{period}-facing-{facing}",
                "input": {"period": period, "facing": facing},
                "expected": natal_expected(period, facing),
            }
        )
    retrieved = datetime.now(UTC).date().isoformat()
    quantities = list(dict.fromkeys(q for c in cases for q in c["expected"]))
    kua_quantities = ["kua", "raw_kua", "solar_year", "boundary_date"]
    annual = [q for q in quantities if q.startswith("annual_")] + ["changeover_date"]
    natal_quantities = [q for q in quantities if q not in kua_quantities + annual]
    return {
        "format": 1,
        "domain": "feng-shui",
        "sources": [
            {
                "name": "Xieji Bianfang Shu",
                "url": "https://zh.wikisource.org/wiki/欽定協紀辨方書_(四庫全書本)",
                "command": "python -m benchmark pull feng-shui (rules recomputed)",
                "retrieved": retrieved,
                "licence": "Public domain text, compiled 1739 to 1741; rules only",
                "citation": (
                    "Qinding Xieji Bianfang Shu, compiled by Yunlu, Mei Gucheng, He Guozong and "
                    "others by imperial order, 1739 to 1741, Siku Quanshu edition. Juan 35 "
                    "(appendix), the section on the nine palaces of men and women: the Kua rule "
                    "for both sexes. Juan 8, the table of the year star entering the centre and "
                    "its worked plate for the jiazi year 1684: the annual centre star, the era "
                    "anchor and the Lo Shu flight path. Juan 34, the note on building works "
                    "between Da Han and Li Chun: the year spirits change at Li Chun"
                ),
                "method": (
                    "A man counts backwards one palace a year from Kan 1, Xun 4 and Dui 7 at the "
                    "jiazi years of the upper, middle and lower eras, a woman forwards from the "
                    "centre 5, Kun 2 and Gen 8. The year star enters the centre at 1, 4 and 7 at "
                    "the same three years and steps back one a year, the same count as a man, "
                    "and the plate flies from the centre to Qian, Dui, Gen, Li, Kan, Kun, Zhen "
                    "and Xun. The year 1684 opened an upper era, so 1864, 180 years on, "
                    "opened the next. The solar year turns at Li Chun."
                ),
                "notes": (
                    "The text records that an older almanac shifted the eras by one and was "
                    "corrected by imperial order in 1717; this domain follows the corrected "
                    "reading, which the other two printed sources share. Its year star table "
                    "is transcribed as a cross check."
                ),
                "applies_to": ["kua", "raw_kua", *[q for q in annual if q != "changeover_date"]],
            },
            {
                "name": "Gujin Tushu Jicheng, Yangzhai Shishu",
                "url": ("https://zh.wikisource.org/wiki/欽定古今圖書集成/博物彙編/藝術典/第675卷"),
                "retrieved": retrieved,
                "licence": "Public domain text, printed 1726; values only",
                "citation": (
                    "Qinding Gujin Tushu Jicheng, 1726, Bowu section, Yishu canon, juan 675, "
                    "Kanyu part 25: Yangzhai Shishu, chapter 2 on the Fu Yuan, the rule for "
                    "starting men and women in the three eras, and the table of the Fu De palace "
                    "for every year of the three jiazi eras"
                ),
                "method": (
                    "States the same rule for both sexes and that a man on the centre 5 lodges "
                    "at Kun and a woman at Gen, with the upper era opening in 1504. Its table of "
                    "the gua for a man and for a woman in each of the 180 years is transcribed "
                    "and reproduced year by year by the rule."
                ),
                "notes": (
                    "Convention chosen where schools differ: the printed era count, not the "
                    "modern shortcut that sums the last two digits of the year. The two agree "
                    "from 1900 to 2099 only, because 100 is not a multiple of 9; the 2100 case "
                    "is where they part. A raw 5 lodges at 2 for a man and at 8 for a woman, as "
                    "printed here."
                ),
                "applies_to": ["kua", "raw_kua"],
            },
            {
                "name": "Shen Shi Xuan Kong Xue",
                "url": "https://www.diancangwang.cn/xuanxuewushu/f6f37803664b/90b563d9cb41.html",
                "retrieved": retrieved,
                "licence": "Public domain text, author died 1906, first printed 1925; rules only",
                "citation": (
                    "Shen Zhureng, Shen Shi Xuan Kong Xue, edited by Shen Zumian, first edition "
                    "1925, revised edition 1933, juan 4: the palm rule for placing stars on the "
                    "nine palaces and the nine period star table of the 24 mountains; the same "
                    "juan names 1864 as the year the upper era opened"
                ),
                "method": (
                    "The period star enters the centre and flies forward. The stars on the "
                    "sitting and facing palaces enter the centre as the mountain and water star "
                    "and fly forward when the mountain in the same dragon position of the home "
                    "palace of that star is yang, in reverse when yin; a 5 takes the polarity "
                    "of the sitting or facing mountain itself. Yang mountains are qian, xun, "
                    "gen and kun, the four human dragons yin, shen, si and hai, and the four "
                    "earth dragons jia, geng, ren and bing; the rest are yin. The table of the "
                    "star on the sitting and facing palace and the two flight directions for "
                    "each sitting mountain and period is transcribed and reproduced."
                ),
                "notes": (
                    "Facing is named as one of the 24 mountains, so every chart is the down gua "
                    "chart; the substitute charts for a bearing near a mountain edge are out of "
                    "scope. Three rows of the readable transcript print a flight that the "
                    "verdict on the same row contradicts (mao sitting period 4, you sitting "
                    "period 1, xun sitting period 6) and are left out of the cross checks."
                ),
                "applies_to": natal_quantities,
            },
            {
                "name": "Hong Kong Observatory Gregorian-Lunar calendar conversion table",
                "url": "https://www.hko.gov.hk/en/gts/time/conversion.htm",
                "command": "python -m benchmark pull feng-shui (one text file per year)",
                "retrieved": retrieved,
                "licence": (
                    "Hong Kong Government open data: free to reproduce for commercial and "
                    "non-commercial use with attribution to the Government and DATA.GOV.HK"
                ),
                "method": (
                    "The Spring Commences (Li Chun) date of each year in Hong Kong Time, UTC+8, "
                    "decides the solar year of a birth date and the changeover of an annual "
                    "plate. A date-only birth is read at the start of its day, as the API "
                    "documents, and the Li Chun instant falls later that day, so a birth on the "
                    "Li Chun date belongs to the outgoing year."
                ),
                "notes": (
                    "Day granular printed charts that count the whole Li Chun day as the new "
                    "year differ from this convention on that one day; the lichun-day case pins "
                    "it. The 2025 case catches a boundary assumed fixed on 4 February."
                ),
                "applies_to": ["solar_year", "boundary_date", "changeover_date"],
            },
        ],
        "families": [
            {"label": "Kua number and the Li Chun year boundary", "quantities": kua_quantities},
            {"label": "Annual flying star plate", "quantities": annual},
            {"label": "Natal period, mountain and water stars", "quantities": natal_quantities},
        ],
        "tolerances": [
            {
                "applies_to": ["boundary_date", "changeover_date"],
                "value": 0,
                "unit": "days",
                "why": (
                    "The tables publish calendar dates, not instants, so a date either matches "
                    "or is a whole day away."
                ),
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": (
                    "A star, a Kua number, a solar year and a flight direction are discrete: "
                    "any miss is a different chart."
                ),
            },
        ],
        "cases": cases,
        "cross_checks": cross_checks(),
    }
