"""Chinese calendar: solar term dates, lunar new year and four pillars against published tables."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

SOLAR_TERMS = "/chinese-astrology/calendar/solar-terms/{year}"
LUNAR_DATE = "/chinese-astrology/calendar/lunar-date"
BAZI_CHART = "/chinese-astrology/bazi/chart"

DOMAIN = Domain(
    id="chinese-calendar",
    title="Chinese calendar",
    authority=(
        "Hong Kong Observatory Gregorian-Lunar conversion tables, "
        "sexagenary cycle from a published anchor day"
    ),
    endpoints=(
        Endpoint("GET", SOLAR_TERMS, "Chinese Astrology"),
        Endpoint("POST", LUNAR_DATE, "Chinese Astrology"),
        Endpoint("POST", BAZI_CHART, "Chinese Astrology"),
    ),
    order=50,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        request = dict(case.input or {})
        if "year" in request:
            terms = api.get(SOLAR_TERMS.format(year=request["year"]))["terms"]
            return {term["id"]: term["localDate"] for term in terms}
        if "lunarYear" in request:
            return {"lunar_new_year": api.post(LUNAR_DATE, request)["gregorianDate"]}
        pillars = api.post(BAZI_CHART, request)["pillars"]
        return {f"{p['position']}_pillar": p["id"] for p in pillars}

    return measure_cases(refs, fetch)
