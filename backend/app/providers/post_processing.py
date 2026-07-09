"""Built-in post-processing adapters.

The repository ships a deterministic "stub" provider so the AI pipeline is
exercised end-to-end without requiring an external service. The provider is
declared through the same interface as a remote OpenAI-compatible adapter and
can be replaced by registering a different `PostProcessingProvider`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx

from app.providers.contracts import (
    PostProcessRequest,
    PostProcessResult,
    ProgressReporter,
    ProviderCapabilities,
)

_FILLER_WORDS = {"um", "uh", "er", "ah", "like", "you know", "i mean"}
_TASKS = frozenset(
    {
        "clean",
        "translate",
        "summary",
        "minutes",
        "action_items",
        "topics",
        "entities",
        "qa",
    }
)


class OpenAICompatiblePostProcessingProvider:
    """OpenAI-compatible chat-completions adapter for transcript post-processing."""

    capabilities = ProviderCapabilities(tasks=_TASKS, is_external=True)

    def __init__(self, provider, api_key: str | None, transport: httpx.BaseTransport | None = None) -> None:
        self.provider = provider
        self.api_key = api_key
        self.transport = transport
        self.key = f"api_provider:{provider.id}" if hasattr(provider, "id") else provider.adapter_key

    def validate_options(self, task: str, options: dict) -> None:
        if task not in self.capabilities.tasks:
            raise ValueError(f"Unsupported post-processing task: {task}")
        _endpoint_url(self.provider.base_url, self.provider.endpoint_path)
        if self.provider.auth_type != "none" and not self.api_key:
            raise ValueError("Provider has no configured credential")

    def process(self, request: PostProcessRequest, report_progress: ProgressReporter) -> PostProcessResult:
        self.validate_options(request.task, request.options)
        report_progress(15, f"Preparing {request.task} request", {})
        headers = {str(key): str(value) for key, value in self.provider.headers.items()}
        headers.setdefault("Content-Type", "application/json")
        if self.provider.auth_type == "bearer" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.provider.auth_type == "api_key" and self.api_key:
            headers["X-API-Key"] = self.api_key

        client_kwargs = {"timeout": self.provider.timeout_seconds, "follow_redirects": False}
        if self.transport is not None:
            client_kwargs["transport"] = self.transport
        with httpx.Client(**client_kwargs) as client:
            response = client.post(
                _endpoint_url(self.provider.base_url, self.provider.endpoint_path),
                headers=headers,
                json={
                    "model": self.provider.model_name,
                    "messages": [
                        {"role": "system", "content": _system_prompt(request.task)},
                        {"role": "user", "content": request.text},
                    ],
                    "temperature": request.options.get("temperature", 0.2),
                },
            )
        response.raise_for_status()
        payload = response.json()
        content = _extract_chat_content(payload)
        report_progress(90, f"Normalising {request.task} response", {})
        return PostProcessResult(
            result=_normalise_provider_content(request.task, content),
            metrics={"provider": self.key, **_usage_metrics(payload)},
        )


class StubPostProcessingProvider:
    """Deterministic local provider used for development and tests.

    Implements a subset of the supported tasks with regex/heuristic logic so
    the rest of the AI pipeline can be developed and validated before an
    external LLM is configured.
    """

    key = "stub"
    capabilities = ProviderCapabilities(tasks=_TASKS)

    def validate_options(self, task: str, options: dict) -> None:
        if task not in self.capabilities.tasks:
            raise ValueError(f"Unsupported post-processing task: {task}")

    def process(self, request: PostProcessRequest, report_progress: ProgressReporter) -> PostProcessResult:
        self.validate_options(request.task, request.options)
        handler = _TASK_HANDLERS.get(request.task, _default_handler)
        report_progress(20, f"Preparing {request.task} pass", {})
        result = handler(request.text, request.options)
        report_progress(95, f"Finalising {request.task} pass", {})
        return PostProcessResult(result=result, metrics={"provider": self.key, "task": request.task})


def _clean(text: str, options: dict) -> dict:
    remove_fillers = options.get("remove_fillers", True)
    collapse_whitespace = options.get("collapse_whitespace", True)
    cleaned = text
    if remove_fillers:
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(word) for word in _FILLER_WORDS) + r")\b", re.IGNORECASE
        )
        cleaned = pattern.sub("", cleaned)
    if collapse_whitespace:
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", cleaned) if sentence.strip()]
    return {
        "cleaned_text": cleaned.strip(),
        "sentences": sentences,
        "removed_filler_words": remove_fillers,
    }


def _summary(text: str, options: dict) -> dict:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    max_sentences = max(1, int(options.get("max_sentences", 5)))
    chosen = sentences[:max_sentences]
    return {"summary": " ".join(chosen), "sentences_used": len(chosen), "total_sentences": len(sentences)}


def _action_items(text: str, options: dict) -> dict:
    keywords = ("must", "should", "need to", "todo", "action:", "follow up", "by friday", "by monday")
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in keywords):
            found.append(sentence.strip())
    return {"action_items": found, "count": len(found)}


def _topics(text: str, options: dict) -> dict:
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", text)
    frequency: dict[str, int] = {}
    for word in words:
        key = word.lower()
        frequency[key] = frequency.get(key, 0) + 1
    top = sorted(frequency.items(), key=lambda item: (-item[1], item[0]))[
        : max(1, int(options.get("max_topics", 8)))
    ]
    return {"topics": [{"term": term, "count": count} for term, count in top]}


def _qa(text: str, options: dict) -> dict:
    qa_pairs: list[dict[str, str]] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if "?" in sentence:
            question, _, answer = sentence.partition("?")
            qa_pairs.append({"question": question.strip() + "?", "answer": answer.strip()})
    return {"questions": qa_pairs, "count": len(qa_pairs)}


def _entities(text: str, options: dict) -> dict:
    entities: dict[str, list[str]] = {"people": [], "organisations": [], "locations": []}
    for match in re.finditer(r"\b(?:Mr|Ms|Dr|Prof)\.?\s+[A-Z][a-z]+", text):
        entities["people"].append(match.group(0))
    for match in re.finditer(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\b", text):
        token = match.group(0)
        if token not in entities["people"] and len(token) > 3:
            entities["organisations"].append(token)
    return {key: sorted(set(value)) for key, value in entities.items()}


def _minutes(text: str, options: dict) -> dict:
    summary = _summary(text, options)["summary"]
    actions = _action_items(text, options)["action_items"]
    topics = _topics(text, options)["topics"]
    return {
        "summary": summary,
        "action_items": actions,
        "topics": [topic["term"] for topic in topics],
    }


def _translate(text: str, options: dict) -> dict:
    """Stub translation: prepends a notice so operators can see this is the stub."""
    target = options.get("target_language", "en")
    return {
        "target_language": target,
        "translation": f"[stub:{target}] {text}",
        "notice": "Stub provider returned; configure a real translation provider for production output.",
    }


def _default_handler(text: str, options: dict) -> dict:
    return {"echo": text, "options": options}


def _system_prompt(task: str) -> str:
    return (
        "You process transcript text. Return compact JSON only. "
        f"The requested task is {task}. Preserve meaning and avoid inventing facts."
    )


def _extract_chat_content(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Provider response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("Provider response choice is invalid")
    message = first.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(first.get("text"), str):
        return first["text"]
    raise ValueError("Provider response did not include text content")


def _normalise_provider_content(task: str, content: str) -> dict:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    if task == "clean":
        return {"cleaned_text": content.strip()}
    if task == "translate":
        return {"translation": content.strip()}
    if task == "summary":
        return {"summary": content.strip()}
    return {"text": content.strip()}


def _usage_metrics(payload: dict) -> dict:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens") if key in usage}


def _endpoint_url(base_url: str | None, endpoint_path: str) -> str:
    if not base_url or not endpoint_path.startswith("/"):
        raise ValueError("Provider URL configuration is invalid")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Provider base URL is invalid")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("External providers must use HTTPS")
    return urljoin(base_url.rstrip("/") + "/", endpoint_path.lstrip("/"))


_TASK_HANDLERS: dict[str, Callable[[str, dict], dict]] = {
    "clean": _clean,
    "summary": _summary,
    "action_items": _action_items,
    "topics": _topics,
    "qa": _qa,
    "entities": _entities,
    "minutes": _minutes,
    "translate": _translate,
}
