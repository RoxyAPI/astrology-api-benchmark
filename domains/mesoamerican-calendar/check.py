"""Mesoamerican calendar: Long Count, Tzolkin and Haab of a date against the GMT definition."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/mesoamerican-astrology/mayan/chart"

DOMAIN = Domain(
    id="mesoamerican-calendar",
    title="Mesoamerican calendar",
    authority="GMT correlation 584283, cross-checked against the FAMSI converter",
    endpoints=(Endpoint("POST", ENDPOINT, "Mesoamerican Astrology"),),
    order=70,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        chart = api.post(ENDPOINT, dict(case.input or {}))
        long_count, tzolkin, haab = chart["longCount"], chart["tzolkin"], chart["haab"]
        return {
            "long_count": long_count["formatted"],
            "days_since_epoch": long_count["daysSinceEpoch"],
            "julian_day_number": long_count["julianDayNumber"],
            "tzolkin_sign": tzolkin["daySign"],
            "tzolkin_number": tzolkin["number"],
            "haab_month": haab["month"],
            "haab_day": haab["day"],
        }

    return measure_cases(refs, fetch)
