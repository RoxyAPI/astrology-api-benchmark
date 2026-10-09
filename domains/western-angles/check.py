"""Western angles: Ascendant, Midheaven and Placidus house cusps in the natal chart."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/astrology/natal-chart"
HOUSE_SYSTEM = "placidus"

DOMAIN = Domain(
    id="western-angles",
    title="Western angles and houses",
    authority="NASA JPL Horizons sidereal time and obliquity, standard spherical astronomy",
    endpoints=(Endpoint("POST", ENDPOINT, "Western Astrology"),),
    order=2,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        assert case.chart is not None
        chart = api.post(ENDPOINT, {**case.chart.request(), "houseSystem": HOUSE_SYSTEM})
        if chart["houseSystem"] != HOUSE_SYSTEM:
            raise ValueError(f"house system {chart['houseSystem']!r} returned, not Placidus")
        values: dict[str, Any] = {
            "Ascendant": chart["ascendant"]["longitude"],
            "Midheaven": chart["midheaven"]["longitude"],
        }
        values |= {f"Cusp {h['number']}": h["longitude"] for h in chart["houses"]}
        return values

    return measure_cases(refs, fetch)
