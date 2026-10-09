"""Western planets: ecliptic longitude of ten bodies and Chiron in the natal chart."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/astrology/natal-chart"

DOMAIN = Domain(
    id="western-planets",
    title="Western planets",
    authority="NASA JPL Horizons",
    endpoints=(Endpoint("POST", ENDPOINT, "Western Astrology"),),
    order=1,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        assert case.chart is not None
        chart = api.post(ENDPOINT, case.chart.request())
        longitudes: dict[str, Any] = {p["name"]: p["longitude"] for p in chart["planets"]}
        return longitudes

    return measure_cases(refs, fetch)
