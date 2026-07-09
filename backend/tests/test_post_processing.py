"""Tests for the built-in stub post-processing provider."""

import httpx

from app.providers.contracts import PostProcessRequest
from app.providers.post_processing import OpenAICompatiblePostProcessingProvider, StubPostProcessingProvider


def _run(task: str, text: str, **options) -> dict:
    provider = StubPostProcessingProvider()
    result = provider.process(PostProcessRequest(text=text, task=task, options=options), lambda *_: None)
    return result.result


def test_clean_removes_filler_words() -> None:
    output = _run("clean", "Um, this is uh the test", remove_fillers=True)
    assert "cleaned_text" in output
    assert "um" not in output["cleaned_text"].lower()
    assert "uh" not in output["cleaned_text"].lower()


def test_summary_uses_configured_max_sentences() -> None:
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    output = _run("summary", text, max_sentences=2)
    assert output["sentences_used"] == 2
    assert "First" in output["summary"] and "Second" in output["summary"]


def test_action_items_extracts_keywords() -> None:
    output = _run("action_items", "We must finish the report. Nice weather today. Need to book travel.")
    assert output["count"] >= 2


def test_topics_returns_frequent_terms() -> None:
    text = "transcription transcription transcription audio audio data data data model"
    output = _run("topics", text, max_topics=3)
    assert len(output["topics"]) == 3
    assert output["topics"][0]["term"] in {"transcription", "audio", "data"}


def test_qa_extracts_question_answer_pairs() -> None:
    text = "What is the plan? We will ship it. Where? On Monday."
    output = _run("qa", text)
    assert output["count"] >= 2
    for pair in output["questions"]:
        assert pair["question"].endswith("?")


def test_openai_compatible_provider_normalizes_chat_completion_response() -> None:
    class _Provider:
        key = "provider-1"
        adapter_key = "openai_compatible"
        name = "OpenAI Compatible"
        base_url = "https://api.example.test"
        endpoint_path = "/v1/chat/completions"
        model_name = "gpt-test"
        auth_type = "bearer"
        headers = {}
        timeout_seconds = 30

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-test"
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"summary":"The meeting covered launch readiness."}',
                    }
                }
            ],
            "usage": {"total_tokens": 42},
        }
        return httpx.Response(200, json=payload)

    provider = OpenAICompatiblePostProcessingProvider(
        _Provider(),
        "sk-test",
        transport=httpx.MockTransport(handler),
    )

    result = provider.process(
        PostProcessRequest(text="Launch readiness was discussed.", task="summary", options={}),
        lambda *_: None,
    )

    assert result.result == {"summary": "The meeting covered launch readiness."}
    assert result.metrics["total_tokens"] == 42
