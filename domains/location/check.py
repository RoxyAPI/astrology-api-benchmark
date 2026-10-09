"""Location: the IANA time zone and the current UTC offset the city search returns for a place."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENDPOINT = "/location/search"
PAGE_SIZE = 50

DOMAIN = Domain(
    id="location",
    title="Location",
    authority="IANA Time Zone Database",
    endpoints=(Endpoint("GET", ENDPOINT, "Location and Timezone"),),
    order=180,
)


def offset_seconds(transitions: list[list[Any]], when: datetime) -> int:
    """UTC offset in seconds in force at ``when``, from ``[instant, seconds]`` rows in order."""
    if when < datetime.fromisoformat(transitions[0][0]):
        raise ValueError(f"{when:%Y-%m-%d} precedes the reference offset table")
    offset: int = transitions[0][1]
    for start, seconds in transitions:
        if datetime.fromisoformat(start) > when:
            break
        offset = seconds
    return offset


def pick_place(cities: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, Any]:
    """The one result matching name, country and province, so an ambiguous name is pinned."""
    wanted = (query["q"].casefold(), query["iso2"], query["province"].casefold())
    matches = [
        c for c in cities if (c["city"].casefold(), c["iso2"], c["province"].casefold()) == wanted
    ]
    if len(matches) != 1:
        raise ValueError(f"{len(matches)} results match {query['q']} in {query['province']}")
    return matches[0]


def check(api: ApiClient, refs: References, now: datetime | None = None) -> list[Measurement]:
    """Measure the zone name and the offset in force at ``now`` (the run instant by default)."""
    when = now or datetime.now(UTC)
    inputs = {case.id: dict(case.input or {}) for case in refs.cases}

    def fetch(case: Case) -> dict[str, Any]:
        query = inputs[case.id]
        found = api.get(ENDPOINT, {"q": query["q"], "limit": PAGE_SIZE})
        place = pick_place(found["cities"], query)
        return {
            "timezone": place["timezone"],
            "utc_offset_seconds": round(place["utcOffset"] * 3600),
        }

    # Offsets move with daylight saving, so the expected one is read from the committed rule
    # table at the run instant instead of being frozen at the pull date.
    dated = replace(
        refs,
        cases=tuple(
            replace(
                case,
                expected={
                    **case.expected,
                    "utc_offset_seconds": offset_seconds(inputs[case.id]["offsets"], when),
                },
            )
            for case in refs.cases
        ),
    )
    return measure_cases(dated, fetch)
