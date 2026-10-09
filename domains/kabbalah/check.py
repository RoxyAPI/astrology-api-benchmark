"""Kabbalah: Mispar Hechrachi and Mispar Gadol word values and the Hebrew date of a civil date."""

from typing import Any

from benchmark import ApiClient, Case, Domain, Endpoint, Measurement, References, measure_cases

GEMATRIA = "/kabbalah/gematria"
BIRTH_PROFILE = "/kabbalah/birth-profile"
CIPHERS = {"mispar-hechrachi": "mispar_hechrachi", "mispar-gadol": "mispar_gadol"}

DOMAIN = Domain(
    id="kabbalah",
    title="Kabbalah",
    authority="Published gematria letter table and the arithmetic Hebrew calendar",
    endpoints=(
        Endpoint("POST", GEMATRIA, "Kabbalah"),
        Endpoint("POST", BIRTH_PROFILE, "Kabbalah"),
    ),
    order=100,
)


def check(api: ApiClient, refs: References) -> list[Measurement]:
    def fetch(case: Case) -> dict[str, Any]:
        given = case.input or {}
        if "gematria" in given:
            body = {**given["gematria"], "ciphers": list(CIPHERS)}
            values = {v["id"]: v["value"] for v in api.post(GEMATRIA, body)["values"]}
            return {name: values[cipher] for cipher, name in CIPHERS.items()}
        date = api.post(BIRTH_PROFILE, given["birth"])["hebrewDate"]
        return {
            "hebrew_year": date["year"],
            "month_number": date["monthNumber"],
            "day": date["day"],
            "leap_year": date["leapYear"],
        }

    return measure_cases(refs, fetch)
