import csv
import io
import json
from collections.abc import Mapping, Sequence
from html import escape
from types import SimpleNamespace

from app.models.domain import Report, TranscriptSegment


def render_export(
    export_format: str,
    segments: Sequence[TranscriptSegment],
    options: dict,
    speaker_by_id: Mapping[object, str] | None = None,
) -> tuple[bytes, str, str]:
    normalized_format = export_format.lower()
    speaker_by_id = speaker_by_id or {}
    if normalized_format == "txt":
        return (
            _render_txt(segments, options, speaker_by_id).encode("utf-8"),
            "text/plain; charset=utf-8",
            "txt",
        )
    if normalized_format == "json":
        return _render_json(segments, options, speaker_by_id).encode("utf-8"), "application/json", "json"
    if normalized_format == "srt":
        return (
            _render_srt(segments, options, speaker_by_id).encode("utf-8"),
            "application/x-subrip; charset=utf-8",
            "srt",
        )
    if normalized_format == "vtt":
        return _render_vtt(segments, options, speaker_by_id).encode("utf-8"), "text/vtt; charset=utf-8", "vtt"
    if normalized_format == "csv":
        return _render_csv(segments, options, speaker_by_id), "text/csv; charset=utf-8", "csv"
    if normalized_format == "md":
        return (
            _render_md(segments, options, speaker_by_id).encode("utf-8"),
            "text/markdown; charset=utf-8",
            "md",
        )
    if normalized_format == "html":
        return (
            _render_html(segments, options, speaker_by_id).encode("utf-8"),
            "text/html; charset=utf-8",
            "html",
        )
    if normalized_format == "docx":
        return (
            _render_docx(segments, options, speaker_by_id),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        )
    if normalized_format == "pdf":
        return _render_pdf(segments, options, speaker_by_id), "application/pdf", "pdf"
    raise ValueError("Unsupported export format")


def render_report_export(export_format: str, report: Report, options: dict) -> tuple[bytes, str, str]:
    normalized_format = export_format.lower()
    if normalized_format == "json":
        return _render_report_json(report).encode("utf-8"), "application/json", "json"
    if normalized_format == "csv":
        return _render_report_csv(report), "text/csv; charset=utf-8", "csv"
    if normalized_format == "md":
        return _render_report_md(report).encode("utf-8"), "text/markdown; charset=utf-8", "md"
    if normalized_format == "html":
        return _render_report_html(report).encode("utf-8"), "text/html; charset=utf-8", "html"
    if normalized_format == "docx":
        return (
            _render_docx(
                _report_as_segments(report),
                {**options, "include_timestamps": False, "title": report.title},
                {},
            ),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        )
    if normalized_format == "pdf":
        return _build_pdf(_report_lines(report)), "application/pdf", "pdf"
    if normalized_format == "srt":
        return _render_report_txt(report).encode("utf-8"), "application/x-subrip; charset=utf-8", "srt"
    if normalized_format == "vtt":
        return _render_report_txt(report).encode("utf-8"), "text/vtt; charset=utf-8", "vtt"
    if normalized_format == "txt":
        return _render_report_txt(report).encode("utf-8"), "text/plain; charset=utf-8", "txt"
    raise ValueError("Unsupported export format")


def _render_txt(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> str:
    include_timestamps = options.get("include_timestamps", True)
    lines = []
    for segment in segments:
        prefix = f"[{_format_timestamp(segment.start_ms, separator=':')}] " if include_timestamps else ""
        lines.append(f"{prefix}{_segment_text(segment, options, speaker_by_id)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _render_json(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> str:
    return json.dumps(
        {
            "segments": [
                {
                    "sequence": segment.sequence,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "speaker_id": str(segment.speaker_id) if getattr(segment, "speaker_id", None) else None,
                    "speaker_label": _speaker_label(segment, options, speaker_by_id),
                    "text": segment.text,
                    "confidence": segment.confidence,
                    "is_unclear": segment.is_unclear,
                }
                for segment in segments
            ]
        },
        ensure_ascii=False,
        indent=2,
    )


def _render_srt(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        start = _format_timestamp(segment.start_ms, separator=",")
        end = _format_timestamp(segment.end_ms, separator=",")
        blocks.append(f"{index}\n{start} --> {end}\n{_segment_text(segment, options, speaker_by_id)}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _render_vtt(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> str:
    blocks = []
    for segment in segments:
        start = _format_timestamp(segment.start_ms, separator=".")
        end = _format_timestamp(segment.end_ms, separator=".")
        blocks.append(f"{start} --> {end}\n{_segment_text(segment, options, speaker_by_id)}")
    return "WEBVTT\n\n" + "\n\n".join(blocks) + ("\n" if blocks else "")


def _render_csv(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    include_speakers = options.get("include_speakers", False)
    header = ["sequence", "start_ms", "end_ms"]
    if include_speakers:
        header.append("speaker_label")
    writer.writerow([*header, "text", "confidence", "is_unclear"])
    for segment in segments:
        row = [segment.sequence, segment.start_ms, segment.end_ms]
        if include_speakers:
            row.append(_speaker_label(segment, options, speaker_by_id) or "")
        writer.writerow(
            [*row, segment.text, segment.confidence or "", "true" if segment.is_unclear else "false"]
        )
    return buffer.getvalue().encode("utf-8")


def _render_md(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> str:
    include_timestamps = options.get("include_timestamps", True)
    lines = ["# Transcript", ""]
    for segment in segments:
        text = _segment_text(segment, options, speaker_by_id)
        if include_timestamps:
            lines.append(f"**[{_format_timestamp(segment.start_ms, separator=':')}]** {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines) + "\n"


def _render_html(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> str:
    title = escape(str(options.get("title", "Transcript")))
    body = "".join(
        "<p>"
        f'<span class="ts">[{escape(_format_timestamp(s.start_ms, separator=":"))}]</span> '
        f"{escape(_segment_text(s, options, speaker_by_id))}</p>"
        for s in segments
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:780px;margin:2rem auto;padding:0 1rem;}"
        ".ts{color:#888;font-family:monospace;margin-right:0.5rem;}</style>"
        f"</head><body><h1>{title}</h1>{body}</body></html>"
    )


def _render_docx(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> bytes:
    """Render a minimal valid DOCX without requiring python-docx.

    The Office Open XML format is a ZIP archive; this implementation writes the
    minimum required parts (`[Content_Types].xml`, `_rels/.rels`,
    `word/document.xml`) using only the standard library.
    """
    import zipfile
    from xml.sax.saxutils import escape as xml_escape

    title = xml_escape(str(options.get("title", "Transcript")))
    paragraphs = []
    for segment in segments:
        prefix = (
            f"[{_format_timestamp(segment.start_ms, separator=':')}] "
            if options.get("include_timestamps", True)
            else ""
        )
        text = xml_escape(f"{prefix}{_segment_text(segment, options, speaker_by_id)}")
        paragraphs.append(f"<w:p><w:r><w:t xml:space='preserve'>{text}</w:t></w:r></w:p>")
    document_xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body>"
        f"<w:p><w:pPr><w:pStyle w:val='Title'/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>"
        + "".join(paragraphs)
        + "<w:sectPr><w:pgSz w:w='12240' w:h='15840'/></w:sectPr>"
        "</w:body></w:document>"
    )
    content_types = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
        "<Default Extension='xml' ContentType='application/xml'/>"
        "<Default Extension='rels' "
        "ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
        "<Override PartName='/word/document.xml' "
        "ContentType='application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document.main+xml'/>"
        "</Types>"
    )
    rels = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
        "<Relationship Id='rId1' "
        "Type='http://schemas.openxmlformats.org/officeDocument/2006/"
        "relationships/officeDocument' Target='word/document.xml'/>"
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _render_pdf(
    segments: Sequence[TranscriptSegment], options: dict, speaker_by_id: Mapping[object, str]
) -> bytes:
    """Render a minimal valid PDF using only the standard library.

    The output is a single-page PDF; long transcripts overflow naturally.
    """
    title = str(options.get("title", "Transcript"))
    lines = [title, ""]
    for segment in segments:
        prefix = (
            f"[{_format_timestamp(segment.start_ms, separator=':')}] "
            if options.get("include_timestamps", True)
            else ""
        )
        lines.append(f"{prefix}{_segment_text(segment, options, speaker_by_id)}")
    return _build_pdf(lines)


def _segment_text(segment: TranscriptSegment, options: dict, speaker_by_id: Mapping[object, str]) -> str:
    text = segment.text.strip()
    label = _speaker_label(segment, options, speaker_by_id)
    return f"{label}: {text}" if label else text


def _speaker_label(
    segment: TranscriptSegment, options: dict, speaker_by_id: Mapping[object, str]
) -> str | None:
    if not options.get("include_speakers", False):
        return None
    speaker_id = getattr(segment, "speaker_id", None)
    if speaker_id is None:
        return None
    return speaker_by_id.get(speaker_id) or speaker_by_id.get(str(speaker_id))


def _render_report_json(report: Report) -> str:
    return json.dumps(
        {
            "id": str(report.id),
            "title": report.title,
            "status": report.status,
            "content": report.content,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )


def _render_report_txt(report: Report) -> str:
    return "\n".join(_report_lines(report)) + "\n"


def _render_report_md(report: Report) -> str:
    lines = [f"# {report.title}", ""]
    summary = report.content.get("summary") if isinstance(report.content, dict) else None
    if isinstance(summary, str) and summary.strip():
        lines.extend([summary.strip(), ""])
    for section in _report_sections(report):
        lines.extend([f"## {section['heading']}", "", section["body"], ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_report_html(report: Report) -> str:
    body = "".join(
        f"<section><h2>{escape(section['heading'])}</h2><p>{escape(section['body'])}</p></section>"
        for section in _report_sections(report)
    )
    summary = report.content.get("summary") if isinstance(report.content, dict) else None
    summary_html = f"<p>{escape(summary.strip())}</p>" if isinstance(summary, str) and summary.strip() else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(report.title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;}"
        "section{margin-top:1.5rem;} h1,h2{color:#0f172a;} p{white-space:pre-wrap;line-height:1.6;}</style>"
        f"</head><body><h1>{escape(report.title)}</h1>{summary_html}{body}</body></html>"
    )


def _render_report_csv(report: Report) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(["heading", "body"])
    summary = report.content.get("summary") if isinstance(report.content, dict) else None
    if isinstance(summary, str) and summary.strip():
        writer.writerow(["Summary", summary.strip()])
    for section in _report_sections(report):
        writer.writerow([section["heading"], section["body"]])
    return buffer.getvalue().encode("utf-8")


def _report_lines(report: Report) -> list[str]:
    lines = [report.title, ""]
    summary = report.content.get("summary") if isinstance(report.content, dict) else None
    if isinstance(summary, str) and summary.strip():
        lines.extend([summary.strip(), ""])
    for section in _report_sections(report):
        lines.extend([section["heading"], section["body"], ""])
    return lines


def _report_as_segments(report: Report) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            sequence=index,
            start_ms=0,
            end_ms=0,
            speaker_id=None,
            text=line,
            confidence=None,
            is_unclear=False,
        )
        for index, line in enumerate([line for line in _report_lines(report) if line.strip()], start=1)
    ]


def _report_sections(report: Report) -> list[dict[str, str]]:
    raw_sections = report.content.get("sections") if isinstance(report.content, dict) else None
    if not isinstance(raw_sections, list):
        return []
    sections = []
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        body = str(section.get("body") or "").strip()
        if heading or body:
            sections.append({"heading": heading or "Section", "body": body})
    return sections


def _build_pdf(lines: list[str]) -> bytes:
    """Construct a minimal PDF document containing the supplied text lines."""
    # Build the content stream
    content_parts = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
    for index, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index == 0:
            content_parts.append("/F1 14 Tf")
            content_parts.append(f"({safe}) Tj")
            content_parts.append("/F1 11 Tf")
            content_parts.append("0 -14 Td")
        else:
            content_parts.append(f"({safe}) Tj")
            content_parts.append("0 -14 Td")
    content_parts.append("ET")
    content_stream = "\n".join(content_parts).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    objects.append(
        b"<< /Length "
        + str(len(content_stream)).encode()
        + b" >>\nstream\n"
        + content_stream
        + b"\nendstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n%\xc2\xa5\xc2\xb1\xc3\xab\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode())
        buffer.write(body)
        buffer.write(b"\nendobj\n")
    xref_offset = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode())
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode())
    buffer.write(b"trailer\n")
    buffer.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    buffer.write(b"startxref\n")
    buffer.write(f"{xref_offset}\n".encode())
    buffer.write(b"%%EOF")
    return buffer.getvalue()


def _format_timestamp(milliseconds: int, separator: str) -> str:
    hours, remainder = divmod(max(0, milliseconds), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}"
