"""The HTTP client every domain check calls: JSON in, JSON out, one key header, standard library."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from benchmark.fetch import USER_AGENT

DEFAULT_TARGET = "https://roxyapi.com/api/v2"
KEY_VARIABLE = "BENCHMARK_API_KEY"
HEADER_VARIABLE = "BENCHMARK_API_KEY_HEADER"
DEFAULT_KEY_HEADER = "X-API-Key"
TIMEOUT_SECONDS = 30.0
ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 2.0
TRANSIENT = frozenset({429, 502, 503, 504, 520, 521, 522, 523, 524})
"""Gateway, edge and rate statuses worth another try; any other error fails the case at once."""
MAX_RETRY_AFTER_SECONDS = 30.0


class ApiError(Exception):
    """A request that returned no usable JSON. The run records the case as MISSING."""


class ConfigError(Exception):
    """The run cannot start: no key, or an unreadable env file."""


class ApiClient:
    """Calls ``{base_url}{path}`` with the API key in ``key_header`` (``X-API-Key`` by default)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = TIMEOUT_SECONDS,
        retry_pause: float = RETRY_PAUSE_SECONDS,
        key_header: str = DEFAULT_KEY_HEADER,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.key_header = key_header
        self.timeout = timeout
        self.retry_pause = retry_pause

    @classmethod
    def from_env(cls, base_url: str, env_file: Path) -> ApiClient:
        """Read the key, and optionally its header name, from the environment, else ``env_file``."""
        file_values = load_env_file(env_file)

        def setting(name: str) -> str:
            return (os.environ.get(name) or file_values.get(name, "")).strip()

        key = setting(KEY_VARIABLE)
        if not key:
            raise ConfigError(f"set {KEY_VARIABLE} in the environment or in {env_file.name}")
        return cls(base_url, key, key_header=setting(HEADER_VARIABLE) or DEFAULT_KEY_HEADER)

    def get(self, path: str, params: Mapping[str, str | int | float] | None = None) -> Any:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        return self.request("GET", f"{path}{query}")

    def post(self, path: str, body: Mapping[str, Any]) -> Any:
        return self.request("POST", path, body)

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        headers = {
            self.key_header: self.api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        return fetch_json(req, f"{method} {path}", self.timeout, self.retry_pause)


def fetch_json(
    req: urllib.request.Request,
    what: str,
    timeout: float = TIMEOUT_SECONDS,
    retry_pause: float = RETRY_PAUSE_SECONDS,
) -> Any:
    """Open ``req`` and decode its JSON, retrying a transient status or a dropped connection."""
    for attempt in range(1, ATTEMPTS + 1):
        last = attempt == ATTEMPTS
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            if last or e.code not in TRANSIENT:
                raise ApiError(f"{what}: HTTP {e.code} {detail}") from None
            _pause(retry_pause, attempt, e.headers.get("Retry-After"))
        except (URLError, TimeoutError) as e:
            if last:
                raise ApiError(f"{what}: {e}") from None
            _pause(retry_pause, attempt, None)
        except json.JSONDecodeError:
            raise ApiError(f"{what}: response is not JSON") from None
    raise AssertionError("unreachable")


def _pause(retry_pause: float, attempt: int, retry_after: str | None) -> None:
    """Back off before a retry: the server Retry-After in seconds when given, capped."""
    wait = retry_pause * attempt
    if retry_after and retry_after.isdigit():
        wait = min(float(retry_after), MAX_RETRY_AFTER_SECONDS)
    time.sleep(wait)


def load_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines; blank lines, comments and a missing file yield nothing."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values
