"""Vedic: Lahiri sidereal grahas, nakshatra, pada, navamsa and the Vimshottari dasha at birth."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

BIRTH_CHART = "/vedic-astrology/birth-chart"
NAVAMSA = "/vedic-astrology/navamsa"
DASHA = "/vedic-astrology/dasha/major"

DOMAIN = Domain(
    id="vedic",
    title="Vedic sidereal chart",
    authority="NASA JPL Horizons with the Lahiri ayanamsa by its published definition",
    endpoints=(
        Endpoint("POST", BIRTH_CHART, "Vedic Astrology"),
        Endpoint("POST", NAVAMSA, "Vedic Astrology"),
        Endpoint("POST", DASHA, "Vedic Astrology"),
    ),
    order=10,
)


def _navamsa_placements(chart: dict[str, Any]) -> list[tuple[str, str]]:
    """(graha, rashi key) for every graha in the rashi-keyed navamsa chart."""
    return [
        (graha["graha"], rashi)
        for rashi, house in chart.items()
        if isinstance(house, dict) and "signs" in house
        for graha in house["signs"]
    ]


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        body = case.chart.request() if case.chart else dict(case.input or {})
        chart = api.post(BIRTH_CHART, body)
        values: dict[str, Any] = {"ayanamsa": chart["frame"]["ayanamsaDegrees"]}
        for name, graha in chart["meta"].items():
            values[name] = graha["longitude"]
            values[f"{name} nakshatra"] = graha["nakshatra"]["key"]
            values[f"{name} pada"] = graha["nakshatra"]["pada"]
        for name, rashi in _navamsa_placements(api.post(NAVAMSA, body)["chart"]):
            values[f"{name} navamsa"] = rashi
        dasha = api.post(DASHA, body)
        values["dasha lord"] = dasha["mahadashas"][0]["planet"]
        values["dasha balance"] = dasha["birthDashaBalance"]["totalDays"]
        return values

    return measure_cases(refs, fetch)
