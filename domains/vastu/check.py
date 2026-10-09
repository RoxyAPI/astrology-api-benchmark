"""Vastu: the entrance pada a main door falls on, against the printed Brihat Samhita enumeration."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

ENTRANCE = "/vastu/entrance"

DOMAIN = Domain(
    id="vastu",
    title="Vastu",
    authority="Brihat Samhita chapter 53 in the Iyer and Kern translations",
    endpoints=(Endpoint("POST", ENTRANCE, "Vastu"),),
    order=80,
)

PLOT = {"width": 90, "depth": 90, "unit": "feet"}
"""A square plot of 90 feet: each of the nine by nine squares is exactly 10 feet."""

CATEGORY = {"auspicious": "gain", "inauspicious": "harm", "mixed": "mixed"}
"""The API labels of a verse effect, mapped onto the three words of the reference rule."""


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        given = dict(case.input or {})
        body: dict[str, Any] = {"plot": PLOT, "facingDegrees": given["facing_degrees"]}
        if "door_position" in given:
            body["doorPosition"] = given["door_position"]
        else:
            body["door"] = {"x": given["door_x"], "y": given["door_y"]}
        entrance = api.post(ENTRANCE, body)
        return {
            "side": entrance["side"],
            "ordinal_on_side": entrance["ordinalOnSide"],
            "pada": entrance["pada"],
            "square": entrance["square"],
            "effect_category": CATEGORY.get(entrance["auspiciousness"], entrance["auspiciousness"]),
        }

    return measure_cases(refs, fetch)
