"""I Ching: the hexagram and trigrams of cast line values, against the King Wen sequence."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

LOOKUP = "/iching/hexagrams/lookup"
HEXAGRAM = "/iching/hexagrams/{number}"
TRIGRAM = "/iching/trigrams/{id}"

DOMAIN = Domain(
    id="i-ching",
    title="I Ching",
    authority="King Wen sequence, cross-checked against Legge and the Unicode Standard",
    endpoints=(
        Endpoint("GET", LOOKUP, "I-Ching"),
        Endpoint("GET", HEXAGRAM, "I-Ching"),
        Endpoint("GET", TRIGRAM, "I-Ching"),
    ),
    order=140,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        given = dict(case.input or {})
        if "hexagram" in given:
            hexagram = api.get(HEXAGRAM.format(number=given["hexagram"]))
            return {
                "hexagram_lines": hexagram["binary"],
                "hexagram_lower_trigram": hexagram["lowerTrigram"],
                "hexagram_upper_trigram": hexagram["upperTrigram"],
                "hexagram_symbol": hexagram["symbol"],
            }
        if "trigram" in given:
            return {"trigram_lines": api.get(TRIGRAM.format(id=given["trigram"]))["binary"]}
        primary = api.get(LOOKUP, {"lines": given["primary_lines"]})
        actual: dict[str, Any] = {
            "primary_hexagram": primary["number"],
            "primary_lower_trigram": primary["lowerTrigram"],
            "primary_upper_trigram": primary["upperTrigram"],
        }
        if "relating_lines" in given:
            actual["relating_hexagram"] = api.get(LOOKUP, {"lines": given["relating_lines"]})[
                "number"
            ]
        return actual

    return measure_cases(refs, fetch)
