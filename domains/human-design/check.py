"""Human Design: the Design moment, the Personality and Design Sun and Earth gates and lines,
and the profile."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

BODYGRAPH = "/human-design/bodygraph"
BODIES = ("Sun", "Earth")

DOMAIN = Domain(
    id="human-design",
    title="Human Design bodygraph",
    authority="NASA JPL Horizons with the 88 degree solar arc and the Rave Mandala",
    endpoints=(Endpoint("POST", BODYGRAPH, "Human Design"),),
    order=40,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        body = case.chart.request() if case.chart else dict(case.input or {})
        chart = api.post(BODYGRAPH, body)
        values: dict[str, Any] = {
            "design instant": chart["designInstantUtc"],
            "profile": chart["profile"],
        }
        for activation in chart["gates"]:
            if activation["planet"] in BODIES:
                name = f"{activation['side']} {activation['planet']}"
                values[f"{name} gate"] = activation["gate"]
                values[f"{name} line"] = activation["line"]
        return values

    return measure_cases(refs, fetch)
