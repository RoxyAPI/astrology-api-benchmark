from __future__ import annotations

import io
import re

from benchmark.console import Console, domain_lines, scorecard_lines, use_color
from benchmark.results import DomainResult, document
from benchmark.schema import Domain, Endpoint, Measurement, Status, Unit
from benchmark.stats import summarize

ANSI = re.compile(r"\x1b\[[0-9;]*[mK]")


def measurement(case: str, deviation: float | None, status: Status, note: str = "") -> Measurement:
    return Measurement(case, "Sun", Unit.ARCSEC, 10.0, 10.0, deviation, 36.0, status, note)


def result(*rows: Measurement) -> DomainResult:
    domain = Domain(
        "western-planets",
        "Western planets",
        "NASA JPL Horizons",
        (Endpoint("POST", "/astrology/natal-chart", "Astrology"),),
        1,
    )
    return DomainResult(domain, rows, summarize(domain.id, rows))


GOOD = result(measurement("a", 0.04, Status.PASS), measurement("b", 0.2, Status.PASS))
BAD = result(measurement("a", 0.04, Status.PASS), measurement("b", 90.0, Status.FAIL))


def lines(res: DomainResult, color: bool) -> list[str]:
    return domain_lines(res, 15, Console(io.StringIO(), color))


def test_color_on_has_marks_and_escapes() -> None:
    line = lines(GOOD, True)[0]
    assert "\x1b[" in line
    plain = ANSI.sub("", line)
    assert "✓" in plain
    assert "Western planets" in plain
    assert "2/2" in plain
    assert "median 0.12" in plain
    assert "max 0.2 arcsec" in plain
    assert "within 1 arcsec" in plain


def test_color_off_is_plain_ascii() -> None:
    text = "\n".join(lines(GOOD, False))
    assert "\x1b" not in text
    assert text.isascii()
    assert "PASS Western planets" in text


def test_fail_line_names_case_and_quantity() -> None:
    plain = lines(BAD, False)
    assert "FAIL Western planets" in plain[0]
    assert "1/2" in plain[0]
    assert plain[-1].strip().startswith("FAIL b Sun: expected 10.0 got 10.0, deviation 90")


def test_missing_line_carries_the_note() -> None:
    missing = result(measurement("a", None, Status.MISSING, "HTTP 503"))
    assert "nothing measured" in lines(missing, False)[0]
    assert lines(missing, False)[-1].strip() == "MISSING a Sun: HTTP 503"


def test_scorecard_box_and_sentence() -> None:
    doc = document("2026-10-09", "https://roxyapi.com/api/v2", [GOOD])
    for color in (True, False):
        box = scorecard_lines([GOOD], doc, Console(io.StringIO(), color))
        plain = [ANSI.sub("", row) for row in box]
        assert len({len(row) for row in plain}) == 1
        assert "1 domains, 2 of 2 values within tolerance" in "\n".join(plain)
        assert "RoxyAPI returned 2 of 2 positions within 1 arcsec" in " ".join(
            part.strip(" |") for part in plain
        )
    assert "FAIL" in "\n".join(
        scorecard_lines(
            [BAD], document("2026-10-09", "https://x.invalid", [BAD]), Console(io.StringIO(), False)
        )
    )


def test_use_color_precedence() -> None:
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    assert use_color(Tty(), {})
    assert not use_color(Tty(), {"NO_COLOR": "1"})
    assert use_color(io.StringIO(), {"FORCE_COLOR": "1"})
    assert use_color(Tty(), {"FORCE_COLOR": "1", "NO_COLOR": "1"})
    assert not use_color(io.StringIO(), {})


def test_header_brand_and_progress() -> None:
    out = io.StringIO()
    console = Console(out, True)
    console.header("https://roxyapi.com/api/v2", "2026-10-09")
    console.start("Western planets")
    text = out.getvalue()
    assert "\x1b[1mRoxy" in text
    assert "\x1b[2mAPI" in text
    assert "2026-10-09" in text
    plain = io.StringIO()
    Console(plain, False).start("Western planets")
    assert plain.getvalue() == ""


def test_failures_are_capped() -> None:
    many = result(*(measurement(f"c{i}", 90.0, Status.FAIL) for i in range(8)))
    plain = lines(many, False)
    assert len(plain) == 1 + 5 + 1
    assert plain[-1].strip() == "and 3 more, all in results/latest.csv"
