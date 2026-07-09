from types import SimpleNamespace

from app.services.exports import render_export


def test_srt_export_uses_required_timestamp_format() -> None:
    segments = [SimpleNamespace(sequence=1, start_ms=1234, end_ms=5678, text="Hello world", confidence=None)]

    content, media_type, extension = render_export("srt", segments, {})

    assert content.decode("utf-8") == "1\n00:00:01,234 --> 00:00:05,678\nHello world\n"
    assert media_type == "application/x-subrip; charset=utf-8"
    assert extension == "srt"
