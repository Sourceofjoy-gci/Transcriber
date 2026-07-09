# Model and Provider Adapter Design

## Core rule

Workflow services speak in task contracts and capabilities. Adapter-specific SDKs, command lines, payload shapes, and model files stay behind adapter boundaries. Adding a provider is a new adapter plus catalog/configuration metadata, not a change to `JobService`.

## Contracts

```python
class TranscriptionProvider(Protocol):
    key: str
    capabilities: ProviderCapabilities

    def validate_options(self, options: TranscriptionOptions) -> None: ...
    def probe(self) -> ProviderHealth: ...
    def transcribe(self, request: TranscriptionRequest, progress: ProgressReporter) -> TranscriptionResult: ...

class PostProcessingProvider(Protocol):
    key: str
    capabilities: ProviderCapabilities

    def validate_options(self, task: PostProcessTask, options: dict) -> None: ...
    def process(self, request: PostProcessRequest, progress: ProgressReporter) -> PostProcessResult: ...

class ModelProvider(Protocol):
    key: str
    def list_catalog(self) -> list[ModelDescriptor]: ...
    def download_model(self, model: ModelDescriptor, progress: ProgressReporter) -> InstalledModelResult: ...
    def verify_model(self, installed: InstalledModel) -> ProviderHealth: ...
    def delete_model(self, installed: InstalledModel) -> None: ...

class StorageProvider(Protocol):
    key: str
    def save(self, source: BinaryIO, object_key: str, content_type: str) -> StoredObject: ...
    def open(self, object_key: str) -> BinaryIO: ...
    def delete(self, object_key: str) -> None: ...
    def signed_download(self, object_key: str, expires_in: timedelta) -> str: ...
```

The concrete implementation uses Pydantic request/result types rather than untyped dictionaries. The displayed interfaces retain the requested conceptual shape while preventing fragile runtime payloads.

## Normalized result types

- `TranscriptionResult`: `detected_language`, `duration_ms`, `text`, ordered `segments`, optional `words`, optional `speakers`, warnings, provider metrics, and cost estimate.
- `SegmentResult`: start/end millisecond offsets, text, optional confidence, provider speaker label, and optional words.
- `PostProcessResult`: structured JSON validated against the requested task schema, Markdown/plain-text rendering where relevant, citations/source segment IDs, warnings, and usage/cost metrics.
- `ProviderCapabilities`: supported tasks, media formats, languages, timestamp and word support, diarization/translation support, maximum input, hardware requirements, settings schema, and egress classification.

## Registry and target resolution

At application startup, adapters register themselves by stable keys such as `faster_whisper`, `openai_compatible_transcription`, and `local_llm_service`. `ProviderRegistry` resolves a user-visible execution target to an enabled installed model or provider configuration, checks tenant policy, validates options against capabilities, and returns a short-lived worker execution context with decrypted credentials only when needed.

No adapter receives a database session or raw HTTP request. Adapters receive a typed request, secure temporary file handle, deadline, cancellation token, progress reporter, and redacted tracing context.

## Initial adapters

| Adapter key                  | Kind                       | Initial use                                      | Notes                                                                                                                                      |
| ---------------------------- | -------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `whisper_local`              | Local transcription/model  | Official Whisper models                          | Runs in worker; supports download catalog metadata and CPU/CUDA choices.                                                                   |
| `faster_whisper`             | Local transcription/model  | Default local engine                             | Preferred first implementation for CTranslate2 performance and word timestamps when supported.                                             |
| `whisper_cpp`                | Local transcription/model  | Lightweight optional backend                     | Wrap binary/library behind an isolated process adapter with strict argument validation.                                                    |
| `generic_rest_transcription` | External transcription     | Custom HTTP APIs                                 | Configurable endpoint/auth/header mapping through a constrained template—not arbitrary server-side request scripting.                      |
| `openai_compatible`          | External/local service     | OpenAI APIs, vLLM, LM Studio-compatible services | Separate transcription and text-generation capabilities; base URL and model are configuration.                                             |
| `local_llm_service`          | Post-processing/multimodal | Ollama, vLLM, LM Studio, Qwen services           | Initially processes transcript text and optional extracted media/image/document references only when endpoint capability declares support. |
| `local_filesystem`           | Storage                    | Local deployment                                 | Root-constrained, checksum-aware object storage.                                                                                           |
| `s3_compatible`              | Storage                    | MinIO/S3 future adapter                          | Presigned uploads/downloads and lifecycle integration.                                                                                     |

## Whisper and media execution

The transcription worker checks model installation, FFmpeg availability, requested device, compute type, and available VRAM before loading a model. Long media is chunked at silence-aware or fixed boundaries with overlap; result timestamps are offset, duplicate boundary tokens are reconciled, and original segment provenance remains retained. OOM errors are classified, the model memory is released, and a retry policy may reduce batch size only if the user/administrator option permits fallback.

## Qwen and multimodal policy

Qwen is represented as model metadata plus a compatible inference adapter, not as a special case in report code. A `multimodal` capability declares accepted input modalities, maximum context, and supported tasks such as summary, correction, image/slide analysis, or report generation. Files sent to such a model follow the same privacy/egress policy as transcription. If a model accepts only text, the UI and API offer transcript processing only.

## Generic external HTTP provider safety

The generic adapter supports declarative request templates with approved authentication methods, static headers, endpoint paths relative to an allowlisted base URL, response field mappings, and timeout/retry settings. It forbids arbitrary URL interpolation, shell commands, JavaScript transforms, and response-driven actions. Secrets are decrypted in worker memory only and are redacted from logs and error messages.

## Adapter test contract

Every adapter supplies unit tests for option validation and response normalization; integration tests use a local fake endpoint/fixture media. A conformance suite verifies cancellation, deadline behavior, progress monotonicity, error classification, secret redaction, and capability reporting before an adapter can be enabled in production.
