"""Pull-time downloads of reference data: one identity, one retry policy, polite pacing.

Only ``domains/*/pull.py`` calls this; a benchmark run reads committed files and never fetches
a reference. Calls to the API under test go through ``benchmark.api`` with the same identity.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from collections.abc import Mapping
from urllib.error import HTTPError, URLError

USER_AGENT = "RoxyAPI-Accuracy-Benchmark/2.0 (+https://github.com/RoxyAPI/astrology-api-benchmark)"
ATTEMPTS = 3
TIMEOUT_SECONDS = 60.0
PAUSE_SECONDS = 1.0
"""Courtesy pause after every reference request; public data services ask for it."""


def get_text(url: str, params: Mapping[str, str] | None = None, encoding: str = "utf-8") -> str:
    """GET ``url`` as text in ``encoding``, retrying transient failures, then pausing."""
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                text: str = response.read().decode(encoding)
            time.sleep(PAUSE_SECONDS)
            return text
        except (HTTPError, URLError, TimeoutError):
            if attempt == ATTEMPTS:
                raise
            time.sleep(PAUSE_SECONDS * attempt * 5)
    raise AssertionError("unreachable")
