from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from benchmark.report import AUTHOR, stamp


def test_stamp_writes_title_author_and_subject(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(path)
    stamp(path, title="Report", subject="Every value within tolerance.")
    meta = PdfReader(path).metadata
    assert meta is not None
    assert (meta.title, meta.author, meta.subject) == (
        "Report",
        AUTHOR,
        "Every value within tolerance.",
    )
    assert len(PdfReader(path).pages) == 1
