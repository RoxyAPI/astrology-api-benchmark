"""Forecast: sign ingress, retrograde station and exact transit instants, in seconds."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

FORECAST = "/forecast/transits"
MONTHLY = "/astrology/transits/monthly"
MONTHLY_SUFFIX = ", monthly table"

DOMAIN = Domain(
    id="forecast",
    title="Forecast events",
    authority="NASA JPL Horizons",
    endpoints=(
        Endpoint("POST", FORECAST, "Forecast"),
        Endpoint("POST", MONTHLY, "Western Astrology"),
    ),
    order=30,
)


def one(rows: list[dict[str, Any]], match: Mapping[str, Any], where: str) -> dict[str, Any]:
    """The single row whose fields equal ``match``; none or several is a response fault."""
    found = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    if len(found) != 1:
        raise ValueError(f"{where}: {len(found)} events match {dict(match)}")
    return found[0]


def monthly_instant(table: Mapping[str, Any], match: Mapping[str, Any]) -> str:
    """The table prints a local ``YYYY-MM-DDTHH:MM`` in the zone it echoes, in hours."""
    row = one(table["transitEvents"], match, MONTHLY)
    zone = timezone(timedelta(hours=table["timezone"]))
    return datetime.fromisoformat(row["datetime"]).replace(tzinfo=zone).astimezone(UTC).isoformat()


def check(api: ApiClient, refs: References) -> list[Measurement]:
    tables: dict[tuple[int, int], Mapping[str, Any]] = {}

    def fetch(case: Case) -> dict[str, Any]:
        given = case.input or {}
        actual: dict[str, Any] = {}
        if "forecast" in given:
            event = given["event"]
            timeline = api.post(FORECAST, given["forecast"])["events"]
            kind = next(q for q in case.expected if not q.endswith(MONTHLY_SUFFIX))
            actual[kind] = one(timeline, event, FORECAST)["datetime"]
        if "monthly" in given:
            request = given["monthly"]
            key = (request["year"], request["month"])
            if key not in tables:
                tables[key] = api.post(MONTHLY, request)
            ingress = given["ingress"]
            actual[f"{ingress['planet']} ingress{MONTHLY_SUFFIX}"] = monthly_instant(
                tables[key], ingress
            )
        return actual

    return measure_cases(refs, fetch)
