"""Tests for additional export formats."""

from types import SimpleNamespace

from app.services.exports import render_export


def _segment(seq: int, start_ms: int, end_ms: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        sequence=seq, start_ms=start_ms, end_ms=end_ms, text=text, confidence=None, is_unclear=False
    )


def test_html_export_escapes_html() -> None:
    segments = [_segment(1, 0, 1000, "<script>alert(1)</script> & 'quoted'")]
    content, media_type, ext = render_export("html", segments, {})
    assert b"<script>" not in content
    assert b"&lt;script&gt;" in content
    assert media_type.startswith("text/html")
    assert ext == "html"


def test_csv_export_quotes_correctly() -> None:
    segments = [_segment(1, 0, 1000, 'Hello, "world"')]
    content, _, _ = render_export("csv", segments, {})
    text = content.decode("utf-8")
    # csv writer with QUOTE_ALL wraps every field including the header
    assert text.startswith('"sequence","start_ms","end_ms","text"')
    assert '"Hello, ""world"""' in text


def test_docx_export_is_valid_zip() -> None:
    import io
    import zipfile

    segments = [_segment(1, 0, 1000, "First"), _segment(2, 1000, 2000, "Second")]
    content, media_type, ext = render_export("docx", segments, {})
    assert ext == "docx"
    assert media_type.startswith("application/vnd.openxmlformats")
    archive = zipfile.ZipFile(io.BytesIO(content))
    assert "[Content_Types].xml" in archive.namelist()
    assert "word/document.xml" in archive.namelist()


def test_pdf_export_is_valid_pdf() -> None:
    segments = [_segment(1, 0, 1000, "Hello world")]
    content, media_type, ext = render_export("pdf", segments, {"title": "Sample"})
    assert ext == "pdf"
    assert media_type == "application/pdf"
    assert content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in content
