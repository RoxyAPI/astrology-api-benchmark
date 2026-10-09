"""Moon phases: the date of each new moon, quarter and full moon against the USNO phase tables."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/astrology/moon-phase/upcoming"

DOMAIN = Domain(
    id="moon-phases",
    title="Moon phases",
    authority="U.S. Naval Observatory primary moon phase tables, Universal Time dates",
    endpoints=(Endpoint("GET", ENDPOINT, "Western Astrology"),),
    order=31,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        request = dict(case.input or {})
        phase = request.pop("phase")
        phases = api.get(ENDPOINT, request)["phases"]
        return {"date": {p["phase"]: p["date"] for p in phases}[phase]}

    return measure_cases(refs, fetch)
