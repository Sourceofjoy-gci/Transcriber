import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent, ReactElement, ReactNode } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  createAutomaticJob,
  getAsset,
  getCurrentSession,
  getJob,
  listApiProviders,
  listInstalledModels,
  listOrganisations,
  listProjects,
  login,
  logout,
  setActiveOrganisationId,
  uploadAsset,
} from "./lib/api";
import type {
  ApiProvider,
  Asset,
  InstalledModel,
  Session,
  TranscriptionJobDetail,
} from "./types";
import {
  estimateProcessingTime,
  formatBytes,
  formatDuration,
  Info,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "./components/common";
import { AIRunsPage } from "./pages/AIRunsPage";
import { AuditLogsPage } from "./pages/AuditLogsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ExportsPage } from "./pages/ExportsPage";
import { JobsPage } from "./pages/JobsPage";
import { AssetsPage } from "./pages/AssetsPage";
import { HelpPage } from "./pages/HelpPage";
import { ModelsPage } from "./pages/ModelsPage";
import { OrganisationsPage } from "./pages/OrganisationsPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ReportTemplatesPage } from "./pages/ReportTemplatesPage";
import { ReportsPage } from "./pages/ReportsPage";
import { RolesPage } from "./pages/RolesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StoragePage } from "./pages/StoragePage";
import { TranscriptViewerPage } from "./pages/TranscriptViewerPage";
import { UsersPage } from "./pages/UsersPage";
import { StatusBadge } from "./components/StatusBadge";

const acceptedExtensions =
  ".mp3,.wav,.m4a,.mp4,.mov,.avi,.webm,.ogg,.flac,.aac";
const terminalJobStatuses = new Set(["completed", "failed", "cancelled"]);
const languageOptions = [
  { value: "", label: "Detect automatically" },
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "pt", label: "Portuguese" },
  { value: "it", label: "Italian" },
  { value: "nl", label: "Dutch" },
  { value: "af", label: "Afrikaans" },
  { value: "zu", label: "Zulu" },
  { value: "xh", label: "Xhosa" },
];

export function App(): ReactElement {
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getCurrentSession,
    retry: false,
  });

  useEffect(() => {
    if (sessionQuery.data?.memberships[0]) {
      setActiveOrganisationId(sessionQuery.data.memberships[0].organisation_id);
    }
  }, [sessionQuery.data]);

  if (sessionQuery.isLoading)
    return <LoadingScreen message="Loading secure workspace…" />;
  if (!sessionQuery.data) {
    return (
      <LoginPage
        onLoggedIn={(session) => {
          queryClient.setQueryData(["session"], session);
        }}
      />
    );
  }
  return (
    <AuthenticatedApp
      session={sessionQuery.data}
      onLoggedOut={() => queryClient.removeQueries()}
    />
  );
}

function AuthenticatedApp({
  session,
  onLoggedOut,
}: {
  session: Session;
  onLoggedOut: () => void;
}): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const organisationsQuery = useQuery({
    queryKey: ["organisations"],
    queryFn: listOrganisations,
    retry: false,
  });

  async function handleLogout(): Promise<void> {
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      onLoggedOut();
      navigate("/login");
      setIsLoggingOut(false);
    }
  }

  const role = session.memberships[0]?.role_code ?? "user";

  return (
    <div className="min-h-screen bg-mist text-ink">
      <header className="border-b border-emerald-950/10 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4">
          <NavLink
            to="/"
            className="flex items-center gap-3 font-bold tracking-tight text-ink"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-moss text-lg text-white">
              T
            </span>
            <span>
              Transcriber{" "}
              <span className="font-normal text-slate-500">Platform</span>
            </span>
          </NavLink>
          <button
            type="button"
            className="rounded-lg border border-slate-300 p-2 text-sm sm:hidden"
            onClick={() => setNavOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            ☰
          </button>
          <nav
            aria-label="Primary navigation"
            className={`${navOpen ? "flex" : "hidden"} absolute left-0 right-0 top-16 z-20 flex-col gap-1 border-b border-slate-200 bg-white p-4 text-sm font-medium shadow-md sm:static sm:flex sm:flex-row sm:items-center sm:gap-1 sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none`}
          >
            <NavigationLink to="/">Dashboard</NavigationLink>
            <NavigationLink to="/upload">Upload</NavigationLink>
            <NavigationLink to="/assets">Assets</NavigationLink>
            <NavigationLink to="/projects">Projects</NavigationLink>
            <NavigationLink to="/jobs">Jobs</NavigationLink>
            <NavigationLink to="/transcripts">Transcripts</NavigationLink>
            <NavigationLink to="/exports">Exports</NavigationLink>
            <NavigationLink to="/reports">Reports</NavigationLink>
            <NavigationLink to="/ai-runs">AI Runs</NavigationLink>
            {(role === "system_administrator" ||
              role === "organisation_administrator") && (
              <>
                <NavigationLink to="/models">Models</NavigationLink>
                <NavigationLink to="/providers">Providers</NavigationLink>
                <NavigationLink to="/report-templates">
                  Templates
                </NavigationLink>
                <NavigationLink to="/organisations">Orgs</NavigationLink>
                <NavigationLink to="/users">Users</NavigationLink>
                <NavigationLink to="/roles">Roles</NavigationLink>
                <NavigationLink to="/audit">Audit</NavigationLink>
                <NavigationLink to="/storage">Storage</NavigationLink>
                <NavigationLink to="/settings">Settings</NavigationLink>
              </>
            )}
            <NavigationLink to="/help">Help</NavigationLink>
          </nav>
          <div className="hidden items-center gap-3 sm:flex">
            {(organisationsQuery.data?.length ?? 0) > 1 && (
              <select
                className="field-input max-w-52 py-1 text-xs"
                value={
                  sessionStorage.getItem("activeOrganisationId") ??
                  session.memberships[0]?.organisation_id ??
                  ""
                }
                onChange={(event) => {
                  setActiveOrganisationId(event.target.value);
                  queryClient.invalidateQueries();
                }}
              >
                {organisationsQuery.data?.map((organisation) => (
                  <option key={organisation.id} value={organisation.id}>
                    {organisation.name}
                  </option>
                ))}
              </select>
            )}
            <div className="text-right text-sm">
              <p className="font-semibold">{session.user.display_name}</p>
              <p className="text-xs text-slate-500">
                {role.replaceAll("_", " ")}
              </p>
            </div>
            <button
              className="button-secondary"
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? <Spinner /> : "Sign out"}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-8">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/transcripts" element={<TranscriptsListPage />} />
          <Route
            path="/transcripts/:transcriptId"
            element={<TranscriptViewerPage />}
          />
          <Route path="/exports" element={<ExportsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/report-templates" element={<ReportTemplatesPage />} />
          <Route path="/ai-runs" element={<AIRunsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/organisations" element={<OrganisationsPage />} />
          <Route path="/providers" element={<ProvidersPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/roles" element={<RolesPage />} />
          <Route path="/audit" element={<AuditLogsPage />} />
          <Route path="/storage" element={<StoragePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function LoginPage({
  onLoggedIn,
}: {
  onLoggedIn: (session: Session) => void;
}): ReactElement {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const loginMutation = useMutation({
    mutationFn: () => login(email, password),
  });

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    setError(null);
    try {
      const session = await loginMutation.mutateAsync();
      onLoggedIn(session);
      navigate("/");
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "Unable to sign in",
      );
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[radial-gradient(circle_at_top_right,_#c6ead9,_#eff7f5_40%,_#f5efe3)] p-5">
      <section className="w-full max-w-md rounded-3xl border border-white/80 bg-white/90 p-8 shadow-xl shadow-emerald-950/10">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-moss text-xl font-bold text-white">
          T
        </span>
        <h1 className="mt-6 text-3xl font-bold tracking-tight">Welcome back</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Sign in to manage sensitive media and transcription work.
        </p>
        <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
          <label className="field-label">
            Email address
            <input
              className="field-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="field-label">
            Password
            <input
              className="field-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={12}
              required
            />
          </label>
          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}
          <button
            className="button-primary w-full"
            type="submit"
            disabled={loginMutation.isPending}
          >
            {loginMutation.isPending ? <Spinner /> : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function UploadPage(): ReactElement {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploadedAsset, setUploadedAsset] = useState<Asset | null>(null);
  const [queuedJobId, setQueuedJobId] = useState<string | null>(null);
  const [autoQueueRequested, setAutoQueueRequested] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [executionTargetKind, setExecutionTargetKind] = useState<
    "automatic" | "local_model" | "api_provider"
  >("automatic");
  const [selectedModelId, setSelectedModelId] = useState("automatic");
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [egressAcknowledged, setEgressAcknowledged] = useState(false);
  const [language, setLanguage] = useState("");
  const [wordTimestamps, setWordTimestamps] = useState(false);
  const [vadFilter, setVadFilter] = useState(true);
  const [chunkLength, setChunkLength] = useState("0");
  const [diarizationEnabled, setDiarizationEnabled] = useState(false);
  const [diarizationSpeakerCount, setDiarizationSpeakerCount] = useState("2");
  const [error, setError] = useState<string | null>(null);
  const queuedAssetIdRef = useRef<string | null>(null);

  const installedModelsQuery = useQuery({
    queryKey: ["installed-models"],
    queryFn: listInstalledModels,
    retry: false,
    refetchInterval: 5000,
  });
  const apiProvidersQuery = useQuery({
    queryKey: ["api-providers"],
    queryFn: listApiProviders,
    retry: false,
    refetchInterval: 10000,
  });
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    retry: false,
  });
  const assetQuery = useQuery({
    queryKey: ["asset", uploadedAsset?.id],
    queryFn: () => getAsset(uploadedAsset!.id),
    enabled: Boolean(uploadedAsset?.id) && uploadedAsset?.status !== "failed",
    refetchInterval: (query) => {
      const asset = query.state.data as Asset | undefined;
      if (
        asset?.status === "ready" ||
        asset?.status === "failed" ||
        asset?.status === "deleted"
      ) {
        return false;
      }
      return 2500;
    },
  });
  const jobQuery = useQuery({
    queryKey: ["job", queuedJobId],
    queryFn: () => getJob(queuedJobId!),
    enabled: Boolean(queuedJobId),
    refetchInterval: (query) => {
      const job = query.state.data as TranscriptionJobDetail | undefined;
      return job && terminalJobStatuses.has(job.status) ? false : 3000;
    },
  });
  const uploadMutation = useMutation({
    mutationFn: () =>
      selectedFile
        ? uploadAsset(selectedFile, setProgress, selectedProjectId || null)
        : Promise.reject(new Error("Select a file first")),
    onSuccess: (asset) => {
      setUploadedAsset(asset);
      setAutoQueueRequested(
        asset.status !== "failed" && asset.status !== "deleted",
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (reason) => {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    },
  });
  const jobMutation = useMutation({
    mutationFn: (assetId: string) =>
      createAutomaticJob(assetId, buildJobRequest()),
    onSuccess: (job) => {
      setQueuedJobId(job.id);
      setAutoQueueRequested(false);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (reason) => {
      queuedAssetIdRef.current = null;
      setAutoQueueRequested(false);
      setError(
        reason instanceof ApiError || reason instanceof Error
          ? reason.message
          : "Unable to queue transcription",
      );
    },
  });

  const enabledModels = (installedModelsQuery.data ?? []).filter(
    isEnabledTranscriptionModel,
  );
  const enabledApiProviders = (apiProvidersQuery.data ?? []).filter(
    isEnabledTranscriptionProvider,
  );
  const effectiveAsset = assetQuery.data ?? uploadedAsset;
  const activeJob = jobQuery.data;
  const transcriptId = activeJob ? transcriptIdFromJob(activeJob) : null;
  const isWaitingForMetadata =
    Boolean(autoQueueRequested) &&
    effectiveAsset !== null &&
    effectiveAsset.status !== "ready" &&
    effectiveAsset.status !== "failed" &&
    effectiveAsset.status !== "deleted";
  const selectedModel =
    enabledModels.find((model) => model.id === selectedModelId) ?? null;
  const selectedProvider =
    enabledApiProviders.find(
      (provider) => provider.id === selectedProviderId,
    ) ?? null;
  const targetSelectionIncomplete =
    executionTargetKind === "local_model"
      ? selectedModelId === "automatic" || selectedModel === null
      : executionTargetKind === "api_provider"
        ? selectedProvider === null || !egressAcknowledged
        : false;

  useEffect(() => {
    if (
      selectedModelId !== "automatic" &&
      !enabledModels.some((model) => model.id === selectedModelId)
    ) {
      setSelectedModelId("automatic");
    }
  }, [enabledModels, selectedModelId]);

  useEffect(() => {
    if (
      selectedProviderId &&
      !enabledApiProviders.some(
        (provider) => provider.id === selectedProviderId,
      )
    ) {
      setSelectedProviderId("");
      setEgressAcknowledged(false);
    }
    if (
      executionTargetKind === "api_provider" &&
      !selectedProviderId &&
      enabledApiProviders[0]
    ) {
      setSelectedProviderId(enabledApiProviders[0].id);
    }
  }, [enabledApiProviders, executionTargetKind, selectedProviderId]);

  useEffect(() => {
    if (
      !autoQueueRequested ||
      !effectiveAsset ||
      effectiveAsset.status !== "ready" ||
      jobMutation.isPending
    ) {
      return;
    }
    if (queuedAssetIdRef.current === effectiveAsset.id) return;
    queuedAssetIdRef.current = effectiveAsset.id;
    jobMutation.mutate(effectiveAsset.id);
  }, [autoQueueRequested, effectiveAsset, jobMutation]);

  function buildJobRequest(): {
    execution_target_kind: "automatic" | "local_model" | "api_provider";
    execution_target_id: string | null;
    egress_acknowledged?: boolean;
    language?: string;
    options: Record<string, unknown>;
  } {
    const options: Record<string, unknown> = {
      vad_filter: vadFilter,
      word_timestamps: wordTimestamps,
    };
    const chunkLengthSeconds = Number(chunkLength);
    if (Number.isFinite(chunkLengthSeconds) && chunkLengthSeconds > 0) {
      options.chunk_length = chunkLengthSeconds;
    }
    const speakerCount = Number(diarizationSpeakerCount);
    if (diarizationEnabled) {
      options.diarization = {
        enabled: true,
        provider: "local_turns",
        speaker_count: Number.isFinite(speakerCount) ? speakerCount : 2,
      };
    }
    if (executionTargetKind === "api_provider") {
      return {
        execution_target_kind: "api_provider",
        execution_target_id: selectedProviderId || null,
        egress_acknowledged: egressAcknowledged,
        language: language || undefined,
        options,
      };
    }
    if (executionTargetKind === "local_model") {
      return {
        execution_target_kind: "local_model",
        execution_target_id:
          selectedModelId === "automatic" ? null : selectedModelId,
        language: language || undefined,
        options,
      };
    }
    return {
      execution_target_kind: "automatic",
      execution_target_id: null,
      language: language || undefined,
      options,
    };
  }

  function selectFile(file: File | undefined): void {
    setSelectedFile(file ?? null);
    setUploadedAsset(null);
    setQueuedJobId(null);
    setAutoQueueRequested(false);
    setError(null);
    setProgress(0);
    setDuration(null);
    queuedAssetIdRef.current = null;
    if (!file) return;
    const media = document.createElement("audio");
    media.preload = "metadata";
    const objectUrl = URL.createObjectURL(file);
    media.onloadedmetadata = () => {
      setDuration(Number.isFinite(media.duration) ? media.duration : null);
      URL.revokeObjectURL(objectUrl);
    };
    media.onerror = () => {
      setDuration(null);
      URL.revokeObjectURL(objectUrl);
    };
    media.src = objectUrl;
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>): void {
    event.preventDefault();
    selectFile(event.dataTransfer.files[0]);
  }

  async function handleUploadAndTranscribe(): Promise<void> {
    setError(null);
    setQueuedJobId(null);
    queuedAssetIdRef.current = null;
    try {
      await uploadMutation.mutateAsync();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    }
  }

  async function queueJob(): Promise<void> {
    if (!effectiveAsset || effectiveAsset.status !== "ready") return;
    queuedAssetIdRef.current = effectiveAsset.id;
    await jobMutation.mutateAsync(effectiveAsset.id);
  }

  return (
    <section className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        eyebrow="New transcription"
        title="Upload and transcribe"
        subtitle="Choose a local model, upload media, and queue transcription after the worker validates the file metadata."
      />
      <article className="rounded-3xl border border-dashed border-emerald-700/40 bg-white p-6 shadow-sm sm:p-8">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.9fr)]">
          <label
            className="grid min-h-64 cursor-pointer place-items-center rounded-2xl bg-mist px-5 py-12 text-center transition hover:bg-emerald-50"
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <span className="text-4xl">↑</span>
            <span className="mt-3 font-semibold">Choose audio or video</span>
            <span className="mt-1 text-sm text-slate-600">
              MP3, WAV, M4A, MP4, MOV, AVI, WEBM, OGG, FLAC, or AAC
            </span>
            <input
              className="sr-only"
              type="file"
              accept={acceptedExtensions}
              onChange={(event) => selectFile(event.target.files?.[0])}
            />
          </label>

          <div className="space-y-4 rounded-2xl border border-slate-200 p-5">
            <div>
              <h2 className="text-base font-semibold text-ink">
                Transcription setup
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Automatic uses the organisation default. External API choices
                require explicit acknowledgement.
              </p>
            </div>
            <label className="field-label">
              Project
              <select
                className="field-input"
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
              >
                <option value="">No project</option>
                {(projectsQuery.data ?? []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              Execution target
              <select
                className="field-input"
                value={executionTargetKind}
                onChange={(event) => {
                  const nextValue = event.target.value as
                    | "automatic"
                    | "local_model"
                    | "api_provider";
                  setExecutionTargetKind(nextValue);
                  setEgressAcknowledged(false);
                }}
              >
                <option value="automatic">Automatic local selection</option>
                <option value="local_model">Installed local model</option>
                <option value="api_provider">External API provider</option>
              </select>
            </label>
            {executionTargetKind === "local_model" && (
              <>
                <label className="field-label">
                  Local model
                  <select
                    className="field-input"
                    value={selectedModelId}
                    onChange={(event) => setSelectedModelId(event.target.value)}
                  >
                    <option value="automatic">
                      Choose an enabled local model
                    </option>
                    {enabledModels.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.catalog.name}
                      </option>
                    ))}
                  </select>
                </label>
                {installedModelsQuery.isError && (
                  <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    Model list is unavailable for this account.
                  </p>
                )}
                {!installedModelsQuery.isError &&
                  installedModelsQuery.isSuccess &&
                  enabledModels.length === 0 && (
                    <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      No enabled local transcription models are available.
                    </p>
                  )}
              </>
            )}
            {executionTargetKind === "api_provider" && (
              <>
                <label className="field-label">
                  API provider
                  <select
                    className="field-input"
                    value={selectedProviderId}
                    onChange={(event) => {
                      setSelectedProviderId(event.target.value);
                      setEgressAcknowledged(false);
                    }}
                  >
                    <option value="">Choose an enabled API provider</option>
                    {enabledApiProviders.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.name}
                      </option>
                    ))}
                  </select>
                </label>
                {apiProvidersQuery.isError && (
                  <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    Provider list is unavailable for this account.
                  </p>
                )}
                {!apiProvidersQuery.isError &&
                  apiProvidersQuery.isSuccess &&
                  enabledApiProviders.length === 0 && (
                    <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      No enabled API transcription providers are available.
                    </p>
                  )}
                <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 rounded border-amber-300 text-fern focus:ring-amber-100"
                    checked={egressAcknowledged}
                    onChange={(event) =>
                      setEgressAcknowledged(event.target.checked)
                    }
                  />
                  <span>
                    I acknowledge this transcription sends media to the selected
                    provider.
                  </span>
                </label>
              </>
            )}
            {executionTargetKind === "automatic" &&
              installedModelsQuery.isError && (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  Model list is unavailable for this account. Automatic
                  selection will use the configured default.
                </p>
              )}
            <label className="field-label">
              Spoken language
              <select
                className="field-input"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
              >
                {languageOptions.map((option) => (
                  <option key={option.value || "auto"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-fern focus:ring-emerald-100"
                  checked={vadFilter}
                  onChange={(event) => setVadFilter(event.target.checked)}
                />
                Voice activity filter
              </label>
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-fern focus:ring-emerald-100"
                  checked={wordTimestamps}
                  onChange={(event) => setWordTimestamps(event.target.checked)}
                />
                Word timestamps
              </label>
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-fern focus:ring-emerald-100"
                  checked={diarizationEnabled}
                  onChange={(event) =>
                    setDiarizationEnabled(event.target.checked)
                  }
                />
                Speaker diarisation
              </label>
            </div>
            <label className="field-label">
              Expected speakers
              <select
                className="field-input"
                value={diarizationSpeakerCount}
                disabled={!diarizationEnabled}
                onChange={(event) =>
                  setDiarizationSpeakerCount(event.target.value)
                }
              >
                <option value="1">1 speaker</option>
                <option value="2">2 speakers</option>
                <option value="3">3 speakers</option>
                <option value="4">4 speakers</option>
                <option value="5">5 speakers</option>
                <option value="6">6 speakers</option>
              </select>
            </label>
            <label className="field-label">
              Long file chunking
              <select
                className="field-input"
                value={chunkLength}
                onChange={(event) => setChunkLength(event.target.value)}
              >
                <option value="0">Off</option>
                <option value="600">10 minute chunks</option>
                <option value="1200">20 minute chunks</option>
                <option value="1800">30 minute chunks</option>
              </select>
            </label>
          </div>
        </div>

        {selectedFile && (
          <div className="mt-6 grid gap-4 rounded-2xl border border-slate-200 p-5 sm:grid-cols-3">
            <Info label="File" value={selectedFile.name} />
            <Info label="Size" value={formatBytes(selectedFile.size)} />
            <Info
              label="Duration"
              value={
                effectiveAsset?.metadata?.duration_ms
                  ? formatDuration(effectiveAsset.metadata.duration_ms / 1000)
                  : duration === null
                    ? "Detecting..."
                    : formatDuration(duration)
              }
            />
            <Info
              label="Model"
              value={targetSummary(
                executionTargetKind,
                selectedModel,
                selectedProvider,
              )}
            />
            <Info
              label="Project"
              value={
                (projectsQuery.data ?? []).find(
                  (project) => project.id === selectedProjectId,
                )?.name ?? "No project"
              }
            />
            <Info
              label="Language"
              value={
                languageOptions.find((option) => option.value === language)
                  ?.label ?? language
              }
            />
            <Info
              label="Diarisation"
              value={
                diarizationEnabled
                  ? `${diarizationSpeakerCount} speaker estimate`
                  : "Off"
              }
            />
            <Info
              label="Estimated processing"
              value={estimateProcessingTime(selectedFile.size)}
            />
            <Info
              label="External API"
              value={
                executionTargetKind === "api_provider"
                  ? (selectedProvider?.name ?? "Provider required")
                  : "Not used"
              }
            />
          </div>
        )}

        {uploadMutation.isPending && (
          <div className="mt-6">
            <div className="mb-2 flex justify-between text-sm font-medium">
              <span>Uploading</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full bg-fern transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {effectiveAsset && !queuedJobId && (
          <div className="mt-6 rounded-2xl bg-slate-50 p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-semibold text-ink">Media status</p>
                <p className="mt-1 text-slate-600">
                  {effectiveAsset.status === "ready"
                    ? "Metadata is ready. The file can be transcribed."
                    : effectiveAsset.status === "failed"
                      ? (effectiveAsset.failure_message ??
                        "Media validation failed.")
                      : "The worker is validating metadata before transcription starts."}
                </p>
              </div>
              <StatusBadge status={effectiveAsset.status} />
            </div>
            {isWaitingForMetadata && (
              <div className="mt-3 flex items-center gap-2 text-slate-600">
                <Spinner /> Queueing will continue automatically when metadata
                is ready.
              </div>
            )}
          </div>
        )}

        {queuedJobId && (
          <div className="mt-6 rounded-2xl border border-emerald-950/10 bg-slate-50 p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-semibold text-ink">Transcription job</p>
                <p className="mt-1 text-slate-600">
                  {activeJob
                    ? `${activeJob.status.replaceAll("_", " ")} at ${activeJob.progress_percent}%`
                    : "Waiting for worker status..."}
                </p>
              </div>
              <Link className="button-secondary" to="/jobs">
                View jobs
              </Link>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-white">
              <div
                className="h-full bg-fern transition-all"
                style={{ width: `${activeJob?.progress_percent ?? 0}%` }}
              />
            </div>
            {activeJob?.error_message && (
              <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-rose-700">
                {activeJob.error_message}
              </p>
            )}
            {transcriptId && (
              <Link
                className="button-primary mt-4"
                to={`/transcripts/${transcriptId}`}
              >
                Review transcript
              </Link>
            )}
          </div>
        )}

        {error && (
          <p className="mt-5 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </p>
        )}
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            className="button-primary"
            type="button"
            disabled={
              !selectedFile ||
              uploadMutation.isPending ||
              jobMutation.isPending ||
              isWaitingForMetadata ||
              targetSelectionIncomplete
            }
            onClick={handleUploadAndTranscribe}
          >
            {uploadMutation.isPending ? <Spinner /> : "Upload and transcribe"}
          </button>
          {effectiveAsset?.status === "ready" &&
            !queuedJobId &&
            !autoQueueRequested && (
              <button
                className="button-secondary"
                type="button"
                onClick={queueJob}
                disabled={jobMutation.isPending || targetSelectionIncomplete}
              >
                {jobMutation.isPending ? <Spinner /> : "Queue transcription"}
              </button>
            )}
          {selectedFile && (
            <button
              className="button-secondary"
              type="button"
              onClick={() => selectFile(undefined)}
            >
              Clear
            </button>
          )}
        </div>
      </article>
    </section>
  );
}

function targetSummary(
  executionTargetKind: "automatic" | "local_model" | "api_provider",
  selectedModel: InstalledModel | null,
  selectedProvider: ApiProvider | null,
): string {
  if (executionTargetKind === "local_model") {
    return selectedModel?.catalog.name ?? "Local model required";
  }
  if (executionTargetKind === "api_provider") {
    return selectedProvider?.name ?? "API provider required";
  }
  return "Automatic local selection";
}

function isEnabledTranscriptionModel(model: InstalledModel): boolean {
  return (
    model.status === "installed" &&
    model.enabled &&
    model.catalog.model_type.includes("transcription")
  );
}

function isEnabledTranscriptionProvider(provider: ApiProvider): boolean {
  return (
    provider.enabled &&
    provider.category === "transcription" &&
    provider.secret_configured &&
    Boolean(provider.model_name?.trim()) &&
    capabilitiesSupportTranscription(provider.capabilities)
  );
}

function capabilitiesSupportTranscription(
  capabilities: Record<string, unknown>,
): boolean {
  if (capabilities.transcription === false) return false;
  const tasks = capabilities.tasks ?? capabilities.supported_tasks;
  if (tasks === undefined) return true;
  if (typeof tasks === "string") return tasks === "transcription";
  return Array.isArray(tasks) && tasks.includes("transcription");
}

function transcriptIdFromJob(job: TranscriptionJobDetail): string | null {
  for (let index = job.events.length - 1; index >= 0; index -= 1) {
    const value = job.events[index].data.transcript_id;
    if (typeof value === "string") return value;
  }
  return null;
}

function TranscriptsListPage(): ReactElement {
  const transcriptsQuery = useQuery({
    queryKey: ["transcripts"],
    queryFn: () =>
      fetch("/api/v1/transcripts", { credentials: "include" }).then((r) =>
        r.json(),
      ),
    refetchInterval: 5000,
  });
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Archive"
        title="Transcripts"
        subtitle="Completed local transcriptions are kept as versioned records, ready for review and export."
      />
      <div className="grid gap-3">
        {(transcriptsQuery.data ?? []).map(
          (transcript: {
            id: string;
            source_provider: string;
            detected_language: string | null;
            language: string | null;
          }) => (
            <Link
              key={transcript.id}
              to={`/transcripts/${transcript.id}`}
              className="group flex items-center justify-between gap-4 rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm transition hover:border-emerald-700/30 hover:shadow-md"
            >
              <div>
                <p className="font-semibold text-ink">
                  Transcript {transcript.id.slice(0, 8)}
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  {transcript.source_provider.replaceAll("_", " ")} ·{" "}
                  {transcript.detected_language ??
                    transcript.language ??
                    "Language detection pending"}
                </p>
              </div>
              <span className="text-sm font-semibold text-fern transition group-hover:translate-x-0.5">
                Review →
              </span>
            </Link>
          ),
        )}
        {!transcriptsQuery.data?.length && (
          <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
            Completed transcripts will appear here.
          </p>
        )}
      </div>
    </section>
  );
}

function NavigationLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}): ReactElement {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `rounded-lg px-3 py-2 transition ${isActive ? "bg-emerald-100 text-moss" : "text-slate-600 hover:bg-slate-100"}`
      }
    >
      {children}
    </NavLink>
  );
}
