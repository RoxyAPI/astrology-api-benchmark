"""Panchang: tithi, yoga, karana at the instant, and vara and sunrise of the local day."""

from datetime import datetime
from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

INSTANT = "/vedic-astrology/panchang/basic"
DAY = "/vedic-astrology/panchang/detailed"

DOMAIN = Domain(
    id="panchang",
    title="Panchang",
    authority="NASA JPL Horizons Sun and Moon longitudes by the classical definitions, "
    "sunrise from the US Naval Observatory",
    endpoints=(
        Endpoint("POST", INSTANT, "Vedic Astrology"),
        Endpoint("POST", DAY, "Vedic Astrology"),
    ),
    order=11,
)


def _offset_text(hours: float) -> str:
    minutes = round(abs(hours) * 60)
    return f"{'-' if hours < 0 else '+'}{minutes // 60:02d}:{minutes % 60:02d}"


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        body = dict(case.input or {})
        panchang = api.post(INSTANT, body)
        values: dict[str, Any] = {
            "tithi": panchang["tithi"]["number"],
            "yoga": panchang["yoga"]["number"],
            "karana": panchang["karana"]["number"],
        }
        if "sunrise" in case.expected:
            # The day route takes the date, not the time, and answers sunrise in the local
            # time of the offset sent, without a zone suffix.
            day = api.post(DAY, {k: v for k, v in body.items() if k != "time"})
            values["vara"] = day["vara"]["name"]
            local = datetime.fromisoformat(day["sunrise"])
            values["sunrise"] = f"{local.isoformat()}{_offset_text(float(body['timezone']))}"
        return values

    return measure_cases(refs, fetch)
