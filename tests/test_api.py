"""The HTTP client against a loopback server, and the env file loader."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from benchmark import ApiClient, ApiError
from benchmark.api import KEY_VARIABLE, ConfigError, load_env_file

SEEN: list[dict[str, Any]] = []


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._answer()

    def do_POST(self) -> None:
        self._answer()

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        SEEN.append({"path": self.path, "key": self.headers["X-API-Key"], "body": body})
        if self.path.startswith("/fail"):
            self._send(422, b'{"error": "bad input"}')
        elif self.path.startswith("/text"):
            self._send(200, b"not json")
        else:
            self._send(200, json.dumps({"ok": True}).encode())

    def _send(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def api() -> Iterator[ApiClient]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    SEEN.clear()
    try:
        yield ApiClient(f"http://127.0.0.1:{server.server_port}/", "k-1", timeout=5)
    finally:
        server.shutdown()
        server.server_close()


def test_post_sends_json_and_the_key_header(api: ApiClient) -> None:
    assert api.post("/astrology/natal-chart", {"date": "2000-01-01"}) == {"ok": True}
    assert SEEN == [
        {"path": "/astrology/natal-chart", "key": "k-1", "body": '{"date": "2000-01-01"}'}
    ]


def test_get_encodes_query_parameters(api: ApiClient) -> None:
    api.get("/moon", {"startDate": "2000-01-01", "count": 2})
    assert SEEN[0]["path"] == "/moon?startDate=2000-01-01&count=2"


@pytest.mark.parametrize(("path", "message"), [("/fail", "HTTP 422"), ("/text", "not JSON")])
def test_unusable_responses_raise_api_error(api: ApiClient, path: str, message: str) -> None:
    with pytest.raises(ApiError, match=message):
        api.post(path, {})


def test_unreachable_target_raises_api_error() -> None:
    with pytest.raises(ApiError):
        ApiClient("http://127.0.0.1:9", "k", timeout=2).get("/x")


def test_env_file_parsing(tmp_path: Path) -> None:
    path = tmp_path / ".env.local"
    path.write_text(
        "# comment\n\nexport A=1\nB = \"two\"\nC='three'\nnot a pair\n", encoding="utf-8"
    )
    assert load_env_file(path) == {"A": "1", "B": "two", "C": "three"}
    assert load_env_file(tmp_path / "absent") == {}


def test_key_comes_from_environment_then_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{KEY_VARIABLE}=from-file\n", encoding="utf-8")
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    assert ApiClient.from_env("https://t", env_file).api_key == "from-file"
    monkeypatch.setenv(KEY_VARIABLE, "from-env")
    assert ApiClient.from_env("https://t", env_file).api_key == "from-env"
    monkeypatch.delenv(KEY_VARIABLE)
    with pytest.raises(ConfigError):
        ApiClient.from_env("https://t", tmp_path / "absent")
