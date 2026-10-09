"""Fixture domain for the discovery tests: the API answers with the measured values directly."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

DOMAIN = Domain(
    id="example",
    title="Example",
    authority="Definition",
    endpoints=(Endpoint("POST", "/example", "Example"),),
    order=0,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        body = case.chart.request() if case.chart else dict(case.input or {})
        values: dict[str, Any] = api.post("/example", body)["values"]
        return values

    return measure_cases(refs, fetch)
