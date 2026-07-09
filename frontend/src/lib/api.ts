import type {
  AIRun,
  AIRunTask,
  ApiProvider,
  ApiProviderUsage,
  Asset,
  AssetDownloadUrl,
  AssetListResponse,
  AuditLog,
  DashboardMetrics,
  ExportCreatePayload,
  ExportRecord,
  HardwareCapabilities,
  InstalledModel,
  MediaDerivativeListResponse,
  MemberDetail,
  ModelCatalogInput,
  ModelCatalogItem,
  ModelTestResult,
  Organisation,
  OrganisationInput,
  Permission,
  Project,
  ProjectInput,
  Report,
  ReportTemplate,
  ReportTemplateInput,
  Role,
  SearchResponse,
  SearchReplaceResponse,
  Session,
  Setting,
  Speaker,
  StorageOverview,
  StoragePurgeResult,
  StructuredSettings,
  StructuredSettingsInput,
  Transcript,
  TranscriptDetail,
  TranscriptionJobDetail,
  TranscriptionJob,
  User,
} from "../types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const mutatingMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let refreshPromise: Promise<Session> | null = null;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function setActiveOrganisationId(organisationId: string): void {
  sessionStorage.setItem("activeOrganisationId", organisationId);
}

export function getActiveOrganisationId(): string | null {
  return sessionStorage.getItem("activeOrganisationId");
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<Session> {
  const session = await request<Session>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (session.memberships[0]) {
    setActiveOrganisationId(session.memberships[0].organisation_id);
  }
  return session;
}

export async function getCurrentSession(): Promise<Session> {
  return request<Session>("/auth/me");
}

export async function logout(): Promise<void> {
  await request("/auth/logout", { method: "POST" });
  sessionStorage.removeItem("activeOrganisationId");
}

export async function refreshSession(): Promise<Session> {
  return refreshAccessSession();
}

export function updateProfile(payload: {
  display_name: string;
}): Promise<Session["user"]> {
  return request<Session["user"]>("/auth/me/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ── Dashboard ───────────────────────────────────────────────────────────────

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  return request<DashboardMetrics>("/dashboard/metrics");
}

export async function listAuditLogs(
  params: {
    limit?: number;
  } = {},
): Promise<AuditLog[]> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return request<AuditLog[]>(`/dashboard/audit-logs${qs ? `?${qs}` : ""}`);
}

export async function getHardwareCapabilities(): Promise<HardwareCapabilities> {
  return request<HardwareCapabilities>("/hardware/capabilities");
}

// ── Assets ──────────────────────────────────────────────────────────────────

export async function listAssets(
  params: {
    limit?: number;
    offset?: number;
    project_id?: string;
    status?: string;
    q?: string;
  } = {},
): Promise<AssetListResponse> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  if (params.project_id) search.set("project_id", params.project_id);
  if (params.status) search.set("status", params.status);
  if (params.q) search.set("q", params.q);
  const qs = search.toString();
  return request<AssetListResponse>(`/assets${qs ? `?${qs}` : ""}`);
}

export async function getAsset(assetId: string): Promise<Asset> {
  return request<Asset>(`/assets/${assetId}`);
}

export async function createAssetDownloadUrl(
  assetId: string,
): Promise<AssetDownloadUrl> {
  return request<AssetDownloadUrl>(`/assets/${assetId}/download-url`, {
    method: "POST",
  });
}

export async function listAssetDerivatives(
  assetId: string,
): Promise<MediaDerivativeListResponse> {
  return request<MediaDerivativeListResponse>(`/assets/${assetId}/derivatives`);
}

export async function deleteAsset(assetId: string): Promise<void> {
  await request(`/assets/${assetId}`, { method: "DELETE" });
}

export async function uploadAsset(
  file: File,
  onProgress: (progress: number) => void,
  projectId?: string | null,
): Promise<Asset> {
  const csrfToken = getCookie("csrf_token");
  const organisationId = getActiveOrganisationId();
  const formData = new FormData();
  formData.append("file", file);

  return new Promise<Asset>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const uploadUrl = projectId
      ? `${apiBaseUrl}/assets/upload?project_id=${encodeURIComponent(projectId)}`
      : `${apiBaseUrl}/assets/upload`;
    xhr.open("POST", uploadUrl);
    xhr.withCredentials = true;
    if (csrfToken) xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    if (organisationId)
      xhr.setRequestHeader("X-Organisation-ID", organisationId);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError(0, "Upload connection failed"));
    xhr.onload = () => {
      const payload = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as Asset);
        return;
      }
      reject(new ApiError(xhr.status, extractError(payload, "Upload failed")));
    };
    xhr.send(formData);
  });
}

// ── Projects ────────────────────────────────────────────────────────────────

export const listProjects = (): Promise<Project[]> => request("/projects");
export const getProject = (id: string): Promise<Project> =>
  request(`/projects/${id}`);
export const createProject = (payload: ProjectInput): Promise<Project> =>
  request("/projects", { method: "POST", body: JSON.stringify(payload) });
export const updateProject = (
  id: string,
  payload: Partial<ProjectInput>,
): Promise<Project> =>
  request(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
export const deleteProject = (id: string): Promise<void> =>
  request(`/projects/${id}`, { method: "DELETE" });

// ── Transcription jobs ──────────────────────────────────────────────────────

export async function listJobs(
  params: { limit?: number; offset?: number; status?: string } = {},
): Promise<TranscriptionJob[]> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  if (params.status) search.set("status", params.status);
  const qs = search.toString();
  return request<TranscriptionJob[]>(
    `/transcription-jobs${qs ? `?${qs}` : ""}`,
  );
}

export async function getJob(jobId: string): Promise<TranscriptionJobDetail> {
  return request<TranscriptionJobDetail>(`/transcription-jobs/${jobId}`);
}

export async function cancelJob(jobId: string): Promise<TranscriptionJob> {
  return request<TranscriptionJob>(`/transcription-jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export async function retryJob(jobId: string): Promise<TranscriptionJob> {
  return request<TranscriptionJob>(`/transcription-jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export async function listJobAttempts(jobId: string): Promise<
  Array<{
    id: string;
    attempt_number: number;
    status: string;
    error_detail: string | null;
    started_at: string | null;
    finished_at: string | null;
  }>
> {
  return request(`/transcription-jobs/${jobId}/attempts`);
}

export async function listJobEvents(jobId: string): Promise<
  Array<{
    id: string;
    sequence: number;
    state: string;
    progress_percent: number;
    message: string;
    data: Record<string, unknown>;
    created_at: string;
  }>
> {
  return request(`/transcription-jobs/${jobId}/events/history`);
}

export async function createAutomaticJob(
  assetId: string,
  options: {
    execution_target_kind?: "automatic" | "local_model" | "api_provider";
    execution_target_id?: string | null;
    egress_acknowledged?: boolean;
    language?: string | null;
    options?: Record<string, unknown>;
  } = {},
): Promise<TranscriptionJob> {
  return request<TranscriptionJob>("/transcription-jobs", {
    method: "POST",
    body: JSON.stringify({
      asset_id: assetId,
      execution_target_kind: options.execution_target_kind ?? "automatic",
      execution_target_id: options.execution_target_id,
      egress_acknowledged: options.egress_acknowledged,
      language: options.language,
      options: options.options ?? {},
    }),
  });
}

// ── Transcripts ─────────────────────────────────────────────────────────────

export async function listTranscripts(
  params: { limit?: number; offset?: number } = {},
): Promise<Transcript[]> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const qs = search.toString();
  return request<Transcript[]>(`/transcripts${qs ? `?${qs}` : ""}`);
}

export async function getTranscript(
  transcriptId: string,
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(`/transcripts/${transcriptId}`);
}

export async function searchTranscript(
  transcriptId: string,
  query: string,
  limit = 50,
): Promise<SearchResponse> {
  const search = new URLSearchParams({ q: query, limit: String(limit) });
  return request<SearchResponse>(
    `/transcripts/${transcriptId}/search?${search.toString()}`,
  );
}

export async function editTranscriptSegment(
  transcriptId: string,
  segmentId: string,
  payload: {
    base_version_id?: string | null;
    text?: string;
    is_unclear?: boolean;
    notes?: string;
    change_summary?: string;
  },
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/segments/${segmentId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function batchEditTranscriptSegments(
  transcriptId: string,
  payload: {
    base_version_id?: string | null;
    edits: Array<{
      segment_id: string;
      text?: string;
      notes?: string | null;
      is_unclear?: boolean;
      speaker_id?: string | null;
    }>;
    change_summary?: string;
  },
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/segments:batch-edit`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function assignTranscriptSegmentSpeaker(
  transcriptId: string,
  segmentId: string,
  payload: { base_version_id?: string | null; speaker_id: string | null },
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/segments/${segmentId}/speaker`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function splitTranscriptSegment(
  transcriptId: string,
  segmentId: string,
  splitAtMs: number,
  baseVersionId?: string | null,
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/segments:split`,
    {
      method: "POST",
      body: JSON.stringify({
        base_version_id: baseVersionId,
        segment_id: segmentId,
        split_at_ms: splitAtMs,
      }),
    },
  );
}

export async function mergeTranscriptSegments(
  transcriptId: string,
  firstSegmentId: string,
  secondSegmentId: string,
  baseVersionId?: string | null,
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/segments:merge`,
    {
      method: "POST",
      body: JSON.stringify({
        base_version_id: baseVersionId,
        first_segment_id: firstSegmentId,
        second_segment_id: secondSegmentId,
      }),
    },
  );
}

export async function annotateTranscriptSegment(
  transcriptId: string,
  segmentId: string,
  payload: {
    base_version_id?: string | null;
    note?: string;
    is_unclear?: boolean;
  },
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(`/transcripts/${transcriptId}/annotations`, {
    method: "POST",
    body: JSON.stringify({ segment_id: segmentId, ...payload }),
  });
}

export async function listTranscriptVersions(transcriptId: string): Promise<
  Array<{
    id: string;
    version_number: number;
    source: string;
    change_summary: string | null;
    created_at: string;
  }>
> {
  return request(`/transcripts/${transcriptId}/versions`);
}

export async function restoreTranscriptVersion(
  transcriptId: string,
  versionId: string,
  baseVersionId?: string | null,
): Promise<Transcript> {
  return request<Transcript>(`/transcripts/${transcriptId}/versions:restore`, {
    method: "POST",
    body: JSON.stringify({
      base_version_id: baseVersionId,
      version_id: versionId,
    }),
  });
}

export async function replaceTranscriptText(
  transcriptId: string,
  payload: {
    base_version_id?: string | null;
    query: string;
    replacement: string;
    replace_all?: boolean;
    case_sensitive?: boolean;
  },
): Promise<SearchReplaceResponse> {
  return request<SearchReplaceResponse>(
    `/transcripts/${transcriptId}/search:replace`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function undoTranscriptOperation(
  transcriptId: string,
  payload: { base_version_id?: string | null },
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/operations:undo`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function redoTranscriptOperation(
  transcriptId: string,
  payload: { base_version_id?: string | null },
): Promise<TranscriptDetail> {
  return request<TranscriptDetail>(
    `/transcripts/${transcriptId}/operations:redo`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function listTranscriptSpeakers(
  transcriptId: string,
): Promise<Speaker[]> {
  return request<Speaker[]>(`/transcripts/${transcriptId}/speakers`);
}

export async function createTranscriptSpeaker(
  transcriptId: string,
  payload: {
    label: string;
    display_name?: string;
    role?: string;
    color?: string;
  },
): Promise<Speaker> {
  return request<Speaker>(`/transcripts/${transcriptId}/speakers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTranscriptSpeaker(
  transcriptId: string,
  speakerId: string,
  payload: { display_name?: string; role?: string; color?: string },
): Promise<Speaker> {
  return request<Speaker>(
    `/transcripts/${transcriptId}/speakers/${speakerId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

// ── Exports ─────────────────────────────────────────────────────────────────

export async function createExport(
  payload: ExportCreatePayload,
): Promise<ExportRecord> {
  return request<ExportRecord>("/exports", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export const listExports = (): Promise<ExportRecord[]> => request("/exports");

export async function getExport(exportId: string): Promise<ExportRecord> {
  return request<ExportRecord>(`/exports/${exportId}`);
}

export function exportDownloadUrl(exportId: string): string {
  return `${apiBaseUrl}/exports/${exportId}/download`;
}

// ── Models ──────────────────────────────────────────────────────────────────

export const listModelCatalog = (): Promise<ModelCatalogItem[]> =>
  request("/model-catalog");
export const createModelCatalogEntry = (
  payload: ModelCatalogInput,
): Promise<ModelCatalogItem> =>
  request("/model-catalog", { method: "POST", body: JSON.stringify(payload) });
export const listInstalledModels = (): Promise<InstalledModel[]> =>
  request("/installed-models");
export const addInstalledModel = (catalogId: string): Promise<InstalledModel> =>
  request(`/installed-models/${catalogId}`, { method: "POST" });
export const downloadInstalledModel = (
  modelId: string,
): Promise<InstalledModel> =>
  request(`/installed-models/${modelId}/download`, { method: "POST" });
export const cancelInstalledModelDownload = (
  modelId: string,
): Promise<InstalledModel> =>
  request(`/installed-models/${modelId}/cancel-download`, { method: "POST" });
export const enableInstalledModel = (
  modelId: string,
): Promise<InstalledModel> =>
  request(`/installed-models/${modelId}/enable`, { method: "POST" });
export const disableInstalledModel = (
  modelId: string,
): Promise<InstalledModel> =>
  request(`/installed-models/${modelId}/disable`, { method: "POST" });
export const deleteInstalledModel = (modelId: string): Promise<void> =>
  request(`/installed-models/${modelId}`, { method: "DELETE" });
export const testInstalledModel = (modelId: string): Promise<ModelTestResult> =>
  request(`/installed-models/${modelId}/test`, { method: "POST" });

// ── API Providers ───────────────────────────────────────────────────────────

export const listApiProviders = (): Promise<ApiProvider[]> =>
  request("/api-providers");
export const getApiProvider = (id: string): Promise<ApiProvider> =>
  request(`/api-providers/${id}`);

export interface ApiProviderInput {
  adapter_key: "openai_compatible" | "generic_rest_transcription";
  name: string;
  category: string;
  base_url?: string | null;
  endpoint_path: string;
  model_name?: string | null;
  auth_type: "bearer" | "api_key" | "none";
  headers: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  timeout_seconds: number;
  retry_limit: number;
  api_key?: string | null;
}

export function createApiProvider(
  input: ApiProviderInput,
): Promise<ApiProvider> {
  return request<ApiProvider>("/api-providers", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateApiProvider(
  id: string,
  patch: ApiProviderInput,
): Promise<ApiProvider> {
  return request<ApiProvider>(`/api-providers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function rotateApiProviderSecret(
  id: string,
  secret: string,
): Promise<ApiProvider> {
  return request<ApiProvider>(`/api-providers/${id}/rotate-secret`, {
    method: "POST",
    body: JSON.stringify({ api_key: secret }),
  });
}

export function testApiProvider(id: string): Promise<ApiProvider> {
  return request(`/api-providers/${id}/test`, { method: "POST" });
}

export function enableApiProvider(id: string): Promise<ApiProvider> {
  return request<ApiProvider>(`/api-providers/${id}/enable`, {
    method: "POST",
  });
}

export function disableApiProvider(id: string): Promise<ApiProvider> {
  return request<ApiProvider>(`/api-providers/${id}/disable`, {
    method: "POST",
  });
}

export function setDefaultApiProvider(id: string): Promise<ApiProvider> {
  return request<ApiProvider>(`/api-providers/${id}/default`, {
    method: "POST",
  });
}

export function deleteApiProvider(id: string): Promise<void> {
  return request(`/api-providers/${id}`, { method: "DELETE" });
}

export function getApiProviderUsage(id: string): Promise<ApiProviderUsage> {
  return request<ApiProviderUsage>(`/api-providers/${id}/usage`);
}

// ── Reports ─────────────────────────────────────────────────────────────────

export const listReports = (): Promise<Report[]> => request("/reports");
export const getReport = (id: string): Promise<Report> =>
  request(`/reports/${id}`);
export const deleteReport = (id: string): Promise<void> =>
  request(`/reports/${id}`, { method: "DELETE" });
export const listReportTemplates = (): Promise<ReportTemplate[]> =>
  request("/reports/templates");

export function createReportTemplate(
  payload: ReportTemplateInput,
): Promise<ReportTemplate> {
  return request<ReportTemplate>("/reports/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateReportTemplate(
  id: string,
  payload: Partial<ReportTemplateInput> & { enabled?: boolean },
): Promise<ReportTemplate> {
  return request<ReportTemplate>(`/reports/templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function enableReportTemplate(id: string): Promise<ReportTemplate> {
  return request<ReportTemplate>(`/reports/templates/${id}/enable`, {
    method: "POST",
  });
}

export function disableReportTemplate(id: string): Promise<ReportTemplate> {
  return request<ReportTemplate>(`/reports/templates/${id}/disable`, {
    method: "POST",
  });
}

export function deleteReportTemplate(id: string): Promise<void> {
  return request(`/reports/templates/${id}`, { method: "DELETE" });
}

export function previewReportTemplate(
  id: string,
  payload: { transcript_id: string; title: string },
): Promise<{ content: Record<string, unknown> }> {
  return request<{ content: Record<string, unknown> }>(
    `/reports/templates/${id}/preview`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function createReport(payload: {
  template_id: string;
  transcript_id: string;
  title: string;
}): Promise<Report> {
  return request<Report>("/reports", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateReport(
  id: string,
  payload: {
    title?: string;
    content?: Record<string, unknown>;
    status?: Report["status"];
  },
): Promise<Report> {
  return request<Report>(`/reports/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ── AI Runs ─────────────────────────────────────────────────────────────────

export function createAIRun(payload: {
  transcript_id: string;
  task: AIRunTask;
  execution_target_kind?: "automatic" | "local_model" | "api_provider";
  execution_target_id?: string | null;
  egress_acknowledged?: boolean;
  options?: Record<string, unknown>;
}): Promise<AIRun> {
  return request<AIRun>("/ai-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listAIRuns(limit = 50): Promise<AIRun[]> {
  return request<AIRun[]>(`/ai-runs?limit=${limit}`);
}

export const getAIRun = (id: string): Promise<AIRun> =>
  request(`/ai-runs/${id}`);

export const cancelAIRun = (id: string): Promise<AIRun> =>
  request<AIRun>(`/ai-runs/${id}/cancel`, { method: "POST" });

export const retryAIRun = (id: string): Promise<AIRun> =>
  request<AIRun>(`/ai-runs/${id}/retry`, { method: "POST" });

// ── Users & Members ─────────────────────────────────────────────────────────

export const listUsers = (): Promise<User[]> => request("/users");
export const listRoles = (): Promise<Role[]> => request("/roles");
export const listMemberships = (): Promise<MemberDetail[]> =>
  request("/users/memberships");

export const listPermissions = (): Promise<Permission[]> =>
  request("/roles/permissions");
export const createRole = (payload: {
  code: string;
  name: string;
  permission_codes: string[];
}): Promise<Role> =>
  request("/roles", { method: "POST", body: JSON.stringify(payload) });
export const updateRole = (
  id: string,
  payload: { name?: string; permission_codes?: string[] },
): Promise<Role> =>
  request(`/roles/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const deleteRole = (id: string): Promise<void> =>
  request(`/roles/${id}`, { method: "DELETE" });

export function createUser(payload: {
  email: string;
  display_name: string;
  password: string;
  role_code: string;
}): Promise<User> {
  return request<User>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUser(
  id: string,
  patch: { display_name?: string; is_active?: boolean; role_code?: string },
): Promise<User> {
  return request<User>(`/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteUser(id: string): Promise<void> {
  return request(`/users/${id}`, { method: "DELETE" });
}

// ── Organisations ───────────────────────────────────────────────────────────

export const listOrganisations = (): Promise<Organisation[]> =>
  request("/organisations");
export const createOrganisation = (
  payload: OrganisationInput,
): Promise<Organisation> =>
  request("/organisations", { method: "POST", body: JSON.stringify(payload) });
export const updateOrganisation = (
  id: string,
  payload: OrganisationInput,
): Promise<Organisation> =>
  request(`/organisations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

// ── Settings ────────────────────────────────────────────────────────────────

export const listSettings = (): Promise<Setting[]> => request("/settings");

export const getStructuredSettings = (): Promise<StructuredSettings> =>
  request("/settings/structured");

export const putStructuredSettings = (
  payload: StructuredSettingsInput,
): Promise<StructuredSettings> =>
  request("/settings/structured", {
    method: "PUT",
    body: JSON.stringify(payload),
  });

export function putSetting(
  key: string,
  value: Record<string, unknown> | string,
): Promise<Setting> {
  const payload: {
    key: string;
    value: Record<string, unknown>;
    is_secret: boolean;
  } = {
    key,
    value: typeof value === "string" ? { value } : value,
    is_secret: false,
  };
  return request<Setting>("/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteSetting(key: string): Promise<void> {
  return request(`/settings/${key}`, { method: "DELETE" });
}

export function getStorageOverview(): Promise<StorageOverview> {
  return request<StorageOverview>("/storage/overview");
}

export function purgeExpiredStorage(): Promise<StoragePurgeResult> {
  return request<StoragePurgeResult>("/storage/purge", { method: "POST" });
}

export function putTaskDefault(
  installedModelId: string,
): Promise<InstalledModel> {
  return request<InstalledModel>("/task-defaults/transcription", {
    method: "PUT",
    body: JSON.stringify({ installed_model_id: installedModelId }),
  });
}

export function getTaskDefault(): Promise<InstalledModel | null> {
  return request<InstalledModel | null>("/task-defaults/transcription");
}

// ── Internal helpers ────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { retryOnUnauthorized?: boolean } = {},
): Promise<T> {
  let response = await sendRequest(path, init);
  if (response.status === 401 && shouldRefreshSession(path, options)) {
    await refreshAccessSession();
    response = await sendRequest(path, init);
  }
  return parseResponse<T>(response);
}

async function refreshAccessSession(): Promise<Session> {
  refreshPromise ??= request<Session>(
    "/auth/refresh",
    { method: "POST" },
    { retryOnUnauthorized: false },
  )
    .then((session) => {
      if (session.memberships[0]) {
        setActiveOrganisationId(session.memberships[0].organisation_id);
      }
      return session;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

function shouldRefreshSession(
  path: string,
  options: { retryOnUnauthorized?: boolean },
): boolean {
  if (options.retryOnUnauthorized === false) return false;
  return path !== "/auth/login" && path !== "/auth/refresh";
}

async function sendRequest(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  const organisationId = getActiveOrganisationId();
  if (organisationId) headers.set("X-Organisation-ID", organisationId);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (init.method && mutatingMethods.has(init.method)) {
    const csrfToken = getCookie("csrf_token");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  return fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const payload = parseJson(await response.text());
  if (!response.ok)
    throw new ApiError(
      response.status,
      extractError(payload, "Request failed"),
    );
  return payload as T;
}

function getCookie(name: string): string | null {
  const prefix = `${name}=`;
  return (
    document.cookie
      .split(";")
      .map((value) => value.trim())
      .find((value) => value.startsWith(prefix))
      ?.slice(prefix.length) ?? null
  );
}

function parseJson(value: string): unknown {
  try {
    return value ? JSON.parse(value) : undefined;
  } catch {
    return undefined;
  }
}

function extractError(payload: unknown, fallback: string): string {
  if (typeof payload === "object" && payload && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0];
      if (first && typeof first === "object" && "msg" in first) {
        return String((first as { msg: unknown }).msg);
      }
    }
  }
  return fallback;
}
