from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmark import spec
from benchmark.__main__ import main
from benchmark.domains import discover
from benchmark.schema import Chart, Endpoint
from benchmark.spec import SpecError, drift, label, link, reference_url

SPEC: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "openapi.json").read_text(encoding="utf-8")
)
NATAL = Endpoint("POST", "/astrology/natal-chart", "Western Astrology")


def test_label_and_reference_url() -> None:
    assert label(NATAL) == "POST /api/v2/astrology/natal-chart"
    assert reference_url(NATAL) == (
        "https://roxyapi.com/api-reference#tag/western-astrology/POST/astrology/natal-chart"
    )
    terms = Endpoint("GET", "/chinese-astrology/calendar/solar-terms/{year}", "Chinese Astrology")
    assert reference_url(terms).endswith(
        "#tag/chinese-astrology/GET/chinese-astrology/calendar/solar-terms/{year}"
    )
    place = Endpoint("GET", "/location/search", "Location and  Timezone")
    assert "#tag/location-and-timezone/GET/location/search" in reference_url(place)
    assert link(NATAL) == {"label": label(NATAL), "url": reference_url(NATAL)}


def test_every_declared_endpoint_is_in_the_spec(charts: dict[str, Chart]) -> None:
    endpoints = [e for d in discover(charts) for e in d.domain.endpoints]
    assert endpoints
    assert drift(endpoints, SPEC) == []


def test_drift_names_a_missing_path_method_or_renamed_tag() -> None:
    renamed = copy.deepcopy(SPEC)
    renamed["paths"]["/astrology/natal-chart"]["post"]["tags"] = ["Astrology"]
    assert drift([NATAL], renamed) == [
        "POST /astrology/natal-chart has tag 'Astrology', declared 'Western Astrology'"
    ]
    assert drift([Endpoint("GET", NATAL.path, NATAL.tag)], SPEC) == [
        "GET /astrology/natal-chart is not in the spec"
    ]
    assert drift([Endpoint("POST", "/gone", "X")], SPEC) == ["POST /gone is not in the spec"]


def test_run_stops_before_any_call_when_the_spec_drifted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    renamed = copy.deepcopy(SPEC)
    del renamed["paths"]["/astrology/natal-chart"]
    monkeypatch.setattr("benchmark.__main__.live_spec", lambda: renamed)
    monkeypatch.setenv("BENCHMARK_API_KEY", "test-key")
    code = main(["run", "--domain", "western-planets", "--out", str(tmp_path)])
    assert code == 2
    assert "POST /astrology/natal-chart is not in the spec" in capsys.readouterr().err
    assert not (tmp_path / "latest.json").exists()


def test_live_spec_refuses_an_unreachable_or_foreign_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("benchmark.api.time.sleep", lambda _seconds: None)
    with pytest.raises(SpecError):
        spec.live_spec("http://127.0.0.1:9/openapi.json")
    other = tmp_path / "other.json"
    other.write_text("[]", encoding="utf-8")
    with pytest.raises(SpecError):
        spec.live_spec(other.as_uri())
