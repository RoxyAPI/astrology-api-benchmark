"""Feng shui: Kua number, annual plate and a natal flying star chart by printed rules."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

KUA = "/feng-shui/kua"
ANNUAL = "/feng-shui/flying-stars/annual/{year}"
NATAL = "/feng-shui/flying-stars/natal"

DOMAIN = Domain(
    id="feng-shui",
    title="Feng shui",
    authority=(
        "Printed Qing almanac and Xuan Kong rules recomputed, Hong Kong Observatory Li Chun dates"
    ),
    endpoints=(
        Endpoint("POST", KUA, "Feng Shui"),
        Endpoint("GET", ANNUAL, "Feng Shui"),
        Endpoint("POST", NATAL, "Feng Shui"),
    ),
    order=60,
)


def _plate(palaces: list[dict[str, Any]], prefix: str, field: str) -> dict[str, Any]:
    return {f"{prefix}_{p['palace'].lower()}": p[field] for p in palaces}


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        request = dict(case.input or {})
        if "gender" in request:
            kua = api.post(KUA, request)
            return {
                "kua": kua["kua"],
                "raw_kua": kua["rawKua"],
                "solar_year": kua["solarYear"],
                "boundary_date": kua["boundaryDate"],
            }
        if "facing" not in request:
            annual = api.get(ANNUAL.format(year=request["year"]))
            return _plate(annual["palaces"], "annual", "star") | {
                "changeover_date": annual["changeoverDate"]
            }
        chart = api.post(NATAL, request)
        actual = {"mountain_flight": chart["mountainFlight"], "water_flight": chart["waterFlight"]}
        for plate in ("period", "mountain", "water"):
            actual |= _plate(chart["palaces"], plate, plate)
        return actual

    return measure_cases(refs, fetch)
