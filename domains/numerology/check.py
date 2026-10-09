"""Numerology: Life Path, Expression and Soul Urge against the published Pythagorean rules."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/numerology/chart"

DOMAIN = Domain(
    id="numerology",
    title="Numerology",
    authority="Pythagorean rules recomputed, cross-checked against published worked examples",
    endpoints=(Endpoint("POST", ENDPOINT, "Numerology"),),
    order=90,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        core = api.post(ENDPOINT, dict(case.input or {}))["coreNumbers"]
        return {
            "life_path": core["lifePath"]["number"],
            "expression": core["expression"]["number"],
            "soul_urge": core["soulUrge"]["number"],
        }

    return measure_cases(refs, fetch)
