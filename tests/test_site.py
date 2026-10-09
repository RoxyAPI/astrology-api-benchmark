from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from benchmark.__main__ import main
from benchmark.claims import headline, labels
from benchmark.domains import DomainError, references_for
from benchmark.paths import RESULTS_DIR
from benchmark.results import CSV_FILE, JSON_FILE, ResultsError
from benchmark.schema import load_charts
from benchmark.site import PDF_FILE, PLACEHOLDER, SITE_URL, SiteError, build, render

SCRIPT = re.compile(r'<script id="report-data" type="application/json">(.*?)</script>', re.DOTALL)


def embedded(html: str) -> Any:
    match = SCRIPT.search(html)
    assert match is not None
    return json.loads(match.group(1))


def copy_results(tmp_path: Path) -> Path:
    for name in (JSON_FILE, CSV_FILE):
        shutil.copyfile(RESULTS_DIR / name, tmp_path / name)
    return tmp_path / JSON_FILE


def test_build_inlines_the_committed_results_with_sources(tmp_path: Path) -> None:
    path = build(out_dir=tmp_path / "dist")
    html = path.read_text(encoding="utf-8")
    assert PLACEHOLDER not in html
    data = embedded(html)
    committed = json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8"))
    assert data["run"] == committed["run"]
    assert [d["id"] for d in data["domains"]] == [d["id"] for d in committed["domains"]]
    for domain in data["domains"]:
        assert domain["sources"] and domain["tolerances"]
        assert all("name" in s and "licence" in s for s in domain["sources"])
    refs = references_for((d["id"] for d in committed["domains"]), load_charts())
    assert data["headline"] == " ".join(headline(committed, labels(refs)))
    assert data["target_host"] == "roxyapi.com"
    planets = next(d for d in data["domains"] if d["id"] == "western-planets")
    assert any(line.startswith("RoxyAPI Chiron: ") for line in planets["quantity_lines"])
    assert data["logo"].startswith("data:image/png;base64,")
    assert data["links"]["pdf"] == SITE_URL + PDF_FILE
    for name in (JSON_FILE, CSV_FILE):
        assert (tmp_path / "dist" / name).read_bytes() == (RESULTS_DIR / name).read_bytes()


def test_render_keeps_data_inert_inside_the_script_element() -> None:
    hostile = {"note": "</script><script>alert(1)</script><!-- & -->"}
    html = render(
        f'<script id="report-data" type="application/json">{PLACEHOLDER}</script>', hostile
    )
    assert html.count("</script>") == 1
    assert "<!--" not in html
    assert embedded(html) == hostile


@pytest.mark.parametrize("template", ["no placeholder", f"{PLACEHOLDER}{PLACEHOLDER}"])
def test_render_refuses_a_template_without_one_placeholder(template: str) -> None:
    with pytest.raises(SiteError):
        render(template, {})


def test_build_refuses_an_unknown_results_format(tmp_path: Path) -> None:
    results = copy_results(tmp_path)
    doc = json.loads(results.read_text(encoding="utf-8"))
    results.write_text(json.dumps({**doc, "format": 999}), encoding="utf-8")
    with pytest.raises(ResultsError):
        build(results, out_dir=tmp_path / "dist")
    assert main(["site", "--results", str(results), "--out", str(tmp_path / "dist")]) == 2


def test_build_refuses_a_result_without_its_domain_folder(tmp_path: Path) -> None:
    results = copy_results(tmp_path)
    doc = json.loads(results.read_text(encoding="utf-8"))
    doc["domains"][0]["id"] = "not-a-domain"
    results.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DomainError):
        build(results, out_dir=tmp_path / "dist")


def test_site_command_writes_the_page(tmp_path: Path) -> None:
    assert main(["site", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "index.html").is_file()
