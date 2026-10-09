"""Biorhythm: the three primary cycles of a birth date on a target date, from the sine."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/biorhythm/reading"

CYCLES = ("physical", "emotional", "intellectual")

DOMAIN = Domain(
    id="biorhythm",
    title="Biorhythm",
    authority="sine cycles of 23, 28 and 33 days, recomputed from the published definition",
    endpoints=(Endpoint("POST", ENDPOINT, "Biorhythm"),),
    order=120,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        reading = api.post(ENDPOINT, dict(case.input or {}))
        actual: dict[str, Any] = {"days_since_birth": reading["daysSinceBirth"]}
        for name in CYCLES:
            cycle = reading["cycles"][name]
            actual[f"{name}_percent"] = cycle["value"]
            actual[f"{name}_raw"] = f"{cycle['rawValue']:.4f}".replace("-0.0000", "0.0000")
        return actual

    return measure_cases(refs, fetch)
