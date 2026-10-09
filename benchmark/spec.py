"""The OpenAPI spec of the API: endpoint labels, API reference links and the drift guard.

Every displayed endpoint and every reference link is built here, so the README and the report
page never hand-roll either. A run fetches the live spec once and stops when a declared
endpoint no longer exists there, so a renamed path or tag can never leave a dead link.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from typing import Any

from benchmark.api import DEFAULT_TARGET, ApiError, fetch_json
from benchmark.fetch import USER_AGENT
from benchmark.schema import Endpoint

SPEC_URL = f"{DEFAULT_TARGET}/openapi.json"
REFERENCE_URL = "https://roxyapi.com/api-reference"
API_PREFIX = urllib.parse.urlsplit(DEFAULT_TARGET).path
"""The version prefix a reader calls, ``/api/v2``, shown before every spec path."""


class SpecError(Exception):
    """The live spec is unreachable, or a declared endpoint is not in it."""


def label(endpoint: Endpoint) -> str:
    """``POST /api/v2/astrology/natal-chart``."""
    return f"{endpoint.method} {API_PREFIX}{endpoint.path}"


def reference_url(endpoint: Endpoint) -> str:
    """The operation in the live API reference. The method must stay upper case to resolve."""
    tag = re.sub(r"\s+", "-", endpoint.tag.strip().lower())
    return f"{REFERENCE_URL}#tag/{tag}/{endpoint.method}{endpoint.path}"


def link(endpoint: Endpoint) -> dict[str, str]:
    """The label and the reference URL, as the report page takes them."""
    return {"label": label(endpoint), "url": reference_url(endpoint)}


def live_spec(url: str = SPEC_URL) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        spec = fetch_json(request, url)
    except ApiError as e:
        raise SpecError(f"cannot read the API spec: {e}") from None
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise SpecError(f"{url}: not an OpenAPI document with paths")
    return spec


def drift(endpoints: Iterable[Endpoint], spec: Mapping[str, Any]) -> list[str]:
    """One line per declared endpoint whose method, path or first tag the spec no longer has."""
    problems = []
    for e in dict.fromkeys(endpoints):
        operation = spec["paths"].get(e.path, {}).get(e.method.lower())
        if not isinstance(operation, dict):
            problems.append(f"{e.method} {e.path} is not in the spec")
            continue
        tags = operation.get("tags") or []
        if not tags or tags[0] != e.tag:
            found = tags[0] if tags else "none"
            problems.append(f"{e.method} {e.path} has tag {found!r}, declared {e.tag!r}")
    return problems
