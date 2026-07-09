from datetime import UTC, datetime
from typing import Any

from app.models.domain import ReportTemplate, Transcript, TranscriptSegment, TranscriptVersion


def build_report_content(
    *,
    title: str,
    transcript: Transcript,
    version: TranscriptVersion,
    template: ReportTemplate | None,
    segments: list[TranscriptSegment],
    minutes: dict[str, Any] | None = None,
) -> dict:
    minutes = minutes or {}
    summary = _string_value(minutes.get("summary")) or _summary_from_segments(segments)
    topics = _string_list(minutes.get("topics"))
    action_items = _string_list(minutes.get("action_items"))
    sections = [
        {"heading": heading, "body": _section_body(heading, summary, topics, action_items, segments, minutes)}
        for heading in _schema_sections(template)
    ]
    return {
        "title": title,
        "transcript_id": str(transcript.id),
        "transcript_version_id": str(version.id),
        "template_kind": template.kind if template else "general",
        "template_name": template.name if template else "General report",
        "summary": summary,
        "action_items": action_items,
        "topics": topics,
        "sections": sections,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _schema_sections(template: ReportTemplate | None) -> list[str]:
    raw_sections = (template.schema or {}).get("sections") if template else None
    if not isinstance(raw_sections, list):
        return ["Executive summary", "Topics discussed", "Action items", "Conclusion"]
    sections = [str(section).strip() for section in raw_sections if str(section).strip()]
    return sections or ["Executive summary", "Topics discussed", "Action items", "Conclusion"]


def _section_body(
    heading: str,
    summary: str,
    topics: list[str],
    action_items: list[str],
    segments: list[TranscriptSegment],
    minutes: dict[str, Any],
) -> str:
    key = heading.lower()
    transcript_excerpt = _summary_from_segments(segments)
    if "summary" in key or "overview" in key:
        return summary
    if "topic" in key:
        return _join_or_default(topics, transcript_excerpt)
    if "action" in key:
        return _join_or_default(action_items, "No action items were identified automatically.")
    if "risk" in key:
        return _join_or_default(
            _string_list(minutes.get("risks")), "No specific risks were identified automatically."
        )
    if "decision" in key:
        return _join_or_default(
            _string_list(minutes.get("decisions")), "No decisions were identified automatically."
        )
    if "attendee" in key:
        return _join_or_default(
            _string_list(minutes.get("attendees")), "Attendees were not captured in transcript metadata."
        )
    if "recommendation" in key:
        return "Review the generated sections and assign owners for any follow-up work."
    if "conclusion" in key:
        return "This report was generated automatically from the transcript. Review before publication."
    if "appendix" in key:
        return transcript_excerpt
    return transcript_excerpt


def _summary_from_segments(segments: list[TranscriptSegment]) -> str:
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    if not text:
        return "No transcript text was available."
    return text[:600]


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _join_or_default(values: list[str], default: str) -> str:
    return "\n".join(values) if values else default
