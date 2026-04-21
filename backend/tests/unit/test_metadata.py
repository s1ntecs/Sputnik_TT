from pathlib import Path

from src.scanning.metadata import extract


def test_text_file_line_and_char_count(tmp_path: Path):
    p = tmp_path / "sample.txt"
    p.write_bytes(b"hello\nworld\n\nend")

    meta = extract(p, "sample.txt", "text/plain", size=p.stat().st_size)

    assert meta["line_count"] == 4
    assert meta["char_count"] == 16
    assert meta["extension"] == ".txt"


def test_text_file_trailing_newline_not_counted_as_extra_line(tmp_path: Path):
    p = tmp_path / "trail.txt"
    p.write_bytes(b"a\nb\n")

    meta = extract(p, "trail.txt", "text/plain", size=p.stat().st_size)
    assert meta["line_count"] == 2


def test_pdf_page_count_ignores_pages_root(tmp_path: Path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(
        b"%PDF-1.4\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R 4 0 R 5 0 R]>> endobj\n"
        b"3 0 obj <</Type /Page>> endobj\n"
        b"4 0 obj <</Type /Page>> endobj\n"
        b"5 0 obj <</Type /Page>> endobj\n"
    )

    meta = extract(p, "doc.pdf", "application/pdf", size=p.stat().st_size)

    assert meta["approx_page_count"] == 3


def test_pdf_with_no_pages_returns_at_least_one(tmp_path: Path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    meta = extract(p, "broken.pdf", "application/pdf", size=p.stat().st_size)
    assert meta["approx_page_count"] == 1


def test_non_text_non_pdf_has_no_counts(tmp_path: Path):
    p = tmp_path / "img.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0")
    meta = extract(p, "img.jpg", "image/jpeg", size=p.stat().st_size)
    assert "line_count" not in meta
    assert "approx_page_count" not in meta
    assert meta["extension"] == ".jpg"
