from app.worker.tasks import _parse_probe


def test_probe_parser_normalizes_ffprobe_output() -> None:
    parsed = _parse_probe(
        {
            "format": {"duration": "12.345", "format_name": "mov,mp4,m4a,3gp,3g2,mj2", "bit_rate": "128000"},
            "streams": [
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
                {"codec_type": "video", "codec_name": "h264"},
            ],
        }
    )

    assert parsed["duration_ms"] == 12345
    assert parsed["container"] == "mov"
    assert parsed["audio_codec"] == "aac"
    assert parsed["video_codec"] == "h264"
    assert parsed["sample_rate_hz"] == 48000
