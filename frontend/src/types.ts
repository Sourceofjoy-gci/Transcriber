export type JobStatus =
  | "queued"
  | "uploading"
  | "extracting_audio"
  | "preprocessing"
  | "transcribing"
  | "post_processing"
  | "completed"
  | "failed"
  | "cancelled";

export type AssetStatus =
  | "uploading"
  | "uploaded"
  | "processing_metadata"
  | "ready"
  | "failed"
  | "deleted";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  last_login_at: string | null;
}

export interface Membership {
  organisation_id: string;
  role_code: string;
  status: string;
}

export interface Session {
  user: User;
  memberships: Membership[];
  csrf_token: string;
}

export interface MediaMetadata {
  duration_ms: number | null;
  container: string | null;
  audio_codec: string | null;
  video_codec: string | null;
  sample_rate_hz: number | null;
  channels: number | null;
  bit_rate: number | null;
}

export interface Asset {
  id: string;
  project_id: string | null;
  original_filename: string;
  content_type: string;
  byte_size: number;
  sha256: string;
  status: AssetStatus;
  failure_code: string | null;
  failure_message: string | null;
  created_at: string;
  metadata: MediaMetadata | null;
}

export interface AssetListResponse {
  items: Asset[];
  next_offset: number | null;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  sensitivity: "standard" | "sensitive" | "restricted";
  retention_days: number | null;
  external_apis_allowed: boolean | null;
  created_at: string;
}

export interface ProjectInput {
  name: string;
  description?: string | null;
  sensitivity?: "standard" | "sensitive" | "restricted";
  retention_days?: number | null;
  external_apis_allowed?: boolean | null;
}

export type MediaDerivativeKind =
  | "waveform"
  | "normalized_audio"
  | "thumbnail"
  | "chunk";

export type MediaDerivativeStatus = "queued" | "ready" | "failed" | "deleted";

export interface MediaDerivative {
  id: string;
  asset_id: string;
  kind: MediaDerivativeKind;
  status: MediaDerivativeStatus;
  content_type: string | null;
  byte_size: number;
  metadata: Record<string, unknown>;
  failure_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface MediaDerivativeListResponse {
  items: MediaDerivative[];
}

export interface AssetDownloadUrl {
  url: string;
  method: "GET";
  expires_at: string;
  headers: Record<string, string>;
}

export interface StorageOverview {
  provider: string;
  healthy: boolean;
  storage_bytes: number;
  original_bytes: number;
  derivative_bytes: number;
  active_assets: number;
  deleted_assets: number;
  legal_hold_assets: number;
  retention_days: number | null;
}

export interface StoragePurgeResult {
  status: string;
  purged_assets: number;
  deleted_objects: number;
}

export interface JobEvent {
  id: string;
  sequence: number;
  state: JobStatus;
  progress_percent: number;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface JobAttempt {
  id: string;
  sequence: number;
  worker: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  error_code: string | null;
  error_message: string | null;
}

export interface TranscriptionJob {
  id: string;
  asset_id: string;
  status: JobStatus;
  progress_percent: number;
  execution_target_kind: string;
  execution_target_id: string | null;
  language: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface TranscriptionJobDetail extends TranscriptionJob {
  events: JobEvent[];
}

export interface DashboardMetrics {
  total_files: number;
  completed_transcriptions: number;
  failed_transcriptions: number;
  jobs_in_progress: number;
  storage_bytes: number;
  total_transcription_seconds: number;
  average_processing_ms: number | null;
  most_used_models: Array<{ installed_model_id: string; count: number }>;
  most_used_providers: Array<{ provider: string; count: number }>;
  recent_jobs: Array<{
    id: string;
    status: string;
    progress_percent: number;
    created_at: string;
    error_code: string | null;
  }>;
  api_cost_estimate: number;
  recent_errors: Array<{
    job_id: string;
    error_code: string | null;
    error_message: string | null;
    created_at: string;
  }>;
}

export interface TranscriptVersion {
  id: string;
  version_number: number;
  source: string;
  change_summary: string | null;
  created_at: string;
}

export interface TranscriptSegment {
  id: string;
  sequence: number;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: string | null;
  is_unclear: boolean;
  notes: string | null;
  speaker_id: string | null;
  speaker_label?: string | null;
  word_count: number;
}

export interface Speaker {
  id: string;
  label: string;
  display_name: string | null;
  role: string | null;
  color: string | null;
}

export interface Transcript {
  id: string;
  job_id: string;
  asset_id: string;
  language: string | null;
  detected_language: string | null;
  source_provider: string;
  status: "processing" | "completed" | "failed";
  active_version: TranscriptVersion | null;
  created_at: string;
}

export interface TranscriptDetail extends Transcript {
  segments: TranscriptSegment[];
}

export interface SearchHit {
  segment_id: string;
  sequence: number;
  start_ms: number;
  end_ms: number;
  snippet: string;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
}

export interface SearchReplaceResponse {
  transcript: TranscriptDetail;
  replacement_count: number;
}

export type ExportFormat =
  | "txt"
  | "json"
  | "srt"
  | "vtt"
  | "csv"
  | "md"
  | "html"
  | "docx"
  | "pdf";

export const ALL_EXPORT_FORMATS: ExportFormat[] = [
  "txt",
  "json",
  "srt",
  "vtt",
  "csv",
  "md",
  "html",
  "docx",
  "pdf",
];

export interface ExportRecord {
  id: string;
  transcript_version_id: string;
  format: ExportFormat;
  status: "queued" | "generating" | "completed" | "failed";
  error_message: string | null;
  created_at: string;
  expires_at: string | null;
}

export interface ExportCreatePayload {
  source_type?: "transcript" | "report";
  transcript_id?: string;
  report_id?: string;
  format: ExportFormat;
  segment_ids?: string[];
  options?: Record<string, unknown>;
}

export interface ModelCatalogItem {
  id: string;
  adapter_key: string;
  model_identifier: string;
  name: string;
  model_type: string;
  source_url: string | null;
  revision: string | null;
  size_bytes: number | null;
  requirements: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  checksum: string | null;
}

export interface ModelCatalogInput {
  adapter_key: string;
  model_identifier: string;
  name: string;
  model_type: string;
  source_url?: string | null;
  revision?: string | null;
  size_bytes?: number | null;
  requirements?: Record<string, unknown>;
  capabilities?: Record<string, unknown>;
  checksum?: string | null;
}

export interface InstalledModel {
  id: string;
  catalog_id: string;
  status: "available" | "downloading" | "installed" | "failed" | "deleting";
  enabled: boolean;
  download_progress: number;
  storage_key: string | null;
  verified_at: string | null;
  last_error: string | null;
  hardware_compatibility: Record<string, unknown>;
  is_default: boolean;
  catalog: ModelCatalogItem;
}

export interface ModelTestResult {
  status: string;
  probe: Record<string, unknown>;
  model_id: string;
}

export interface ApiProvider {
  id: string;
  adapter_key: "openai_compatible" | "generic_rest_transcription";
  name: string;
  category: string;
  base_url: string | null;
  endpoint_path: string;
  model_name: string | null;
  auth_type: "bearer" | "api_key" | "none";
  headers: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  enabled: boolean;
  is_default: boolean;
  secret_configured: boolean;
  timeout_seconds: number;
  retry_limit: number;
  last_error: string | null;
  last_tested_at: string | null;
}

export interface ApiProviderUsage {
  provider_id: string;
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  total_duration_ms: number;
  estimated_cost_usd: number;
  recent_calls: Array<{
    id: string;
    job_id: string | null;
    task: string;
    status: string;
    duration_ms: number | null;
    estimated_cost: string | null;
    error_code: string | null;
    created_at: string;
  }>;
}

export interface ReportTemplate {
  id: string;
  kind: string;
  name: string;
  description?: string | null;
  schema: Record<string, unknown>;
  prompt_template?: string | null;
  enabled: boolean;
  is_builtin: boolean;
}

export interface ReportTemplateInput {
  name: string;
  kind: string;
  schema: Record<string, unknown>;
  prompt_template?: string | null;
}

export interface Report {
  id: string;
  transcript_version_id: string;
  template_id: string | null;
  title: string;
  status: "queued" | "generating" | "completed" | "failed";
  content: Record<string, unknown>;
  error_message?: string | null;
  created_by_id?: string;
  created_at: string;
  completed_at?: string | null;
}

export type AIRunTask =
  | "clean"
  | "summary"
  | "minutes"
  | "action_items"
  | "topics"
  | "entities"
  | "qa"
  | "translate";

export const ALL_AI_RUN_TASKS: AIRunTask[] = [
  "clean",
  "translate",
  "summary",
  "minutes",
  "action_items",
  "topics",
  "entities",
  "qa",
];

export interface AIRun {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  task: AIRunTask;
  transcript_id: string;
  transcript_version_id: string;
  execution_target_kind: "automatic" | "local_model" | "api_provider";
  execution_target_id: string | null;
  progress_percent: number;
  progress_message: string | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AIRunCreateInput {
  transcript_id: string;
  task: AIRunTask;
  execution_target_kind?: "automatic" | "local_model" | "api_provider";
  execution_target_id?: string | null;
  egress_acknowledged?: boolean;
  options?: Record<string, unknown>;
}

export interface AuditLog {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLog[];
  total: number;
  next_offset: number | null;
}

export interface Role {
  id: string;
  code: string;
  name: string;
  is_system?: boolean;
  permissions: string[];
}

export interface Permission {
  id: string;
  code: string;
  description: string;
}

export interface Organisation {
  id: string;
  name: string;
  slug: string;
  external_apis_allowed: boolean;
  local_only_enforced: boolean;
  retention_days: number | null;
  role_code: string | null;
  is_current: boolean;
}

export interface OrganisationInput {
  name?: string;
  external_apis_allowed?: boolean | null;
  local_only_enforced?: boolean | null;
  retention_days?: number | null;
}

export interface StructuredSettings {
  organisation: {
    id: string;
    name: string;
    retention_days: number | null;
    external_apis_allowed: boolean;
    local_only_enforced: boolean;
  };
  upload: Record<string, unknown>;
  queue: Record<string, unknown>;
  ai: Record<string, unknown>;
}

export interface StructuredSettingsInput {
  organisation?: {
    retention_days?: number | null;
    external_apis_allowed?: boolean | null;
    local_only_enforced?: boolean | null;
  };
  upload?: Record<string, unknown>;
  queue?: Record<string, unknown>;
  ai?: Record<string, unknown>;
}

export interface Setting {
  key: string;
  value: Record<string, unknown> | string;
  is_secret: boolean;
  updated_at: string | null;
}

export interface HardwareCapabilities {
  cpu_cores: number;
  total_memory_bytes: number;
  has_cuda: boolean;
  has_metal: boolean;
  detected_gpus: Array<{ name: string; memory_bytes: number | null }>;
}

export interface MemberDetail {
  id: string;
  user_id: string;
  organisation_id: string;
  role_id: string;
  role_code: string;
  status: string;
  created_at: string;
}
