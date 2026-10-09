"""Ayurveda: season edges for a date, in both zodiacs, and the sunrise anchored dosha day."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

RITUCHARYA = "/ayurveda/ritucharya"
DINACHARYA = "/ayurveda/dinacharya"

DOMAIN = Domain(
    id="ayurveda",
    title="Ayurveda",
    authority="NASA JPL Horizons Sun ingress by the classical season rule, sunrise from the "
    "US Naval Observatory",
    endpoints=(
        Endpoint("POST", RITUCHARYA, "Ayurveda"),
        Endpoint("POST", DINACHARYA, "Ayurveda"),
    ),
    order=130,
)


def season_values(body: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    ritu = response["ritu"]
    if body.get("hemisphere") == "southern":
        return {"southern ritu": ritu["id"]}
    prefix = "sidereal " if body.get("rituZodiac") == "nirayana" else ""
    return {
        f"{prefix}ritu": ritu["id"],
        f"{prefix}ritu start": ritu["start"],
        f"{prefix}ritu end": ritu["end"],
    }


def day_values(response: dict[str, Any]) -> dict[str, Any]:
    """The period boundaries by their span and dosha, so a reordered list is still read right."""
    periods = response["doshaPeriods"]
    start = {(p["span"], p["dosha"]): p["start"] for p in periods}
    return {
        "sunrise": response["sunrise"],
        "sunset": response["sunset"],
        "next sunrise": response["nextSunrise"],
        "brahma muhurta start": response["brahmaMuhurta"]["start"],
        "brahma muhurta end": response["brahmaMuhurta"]["end"],
        "day pitta start": start["day", "pitta"],
        "day vata start": start["day", "vata"],
        "night pitta start": start["night", "pitta"],
        "night vata start": start["night", "vata"],
        "dosha order": " ".join(p["dosha"] for p in periods),
    }


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        given = case.input or {}
        if "ritucharya" in given:
            body = dict(given["ritucharya"])
            return season_values(body, api.post(RITUCHARYA, body))
        return day_values(api.post(DINACHARYA, dict(given["dinacharya"])))

    return measure_cases(refs, fetch)
