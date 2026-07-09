import { useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createApiProvider,
  deleteApiProvider,
  disableApiProvider,
  enableApiProvider,
  listApiProviders,
  rotateApiProviderSecret,
  setDefaultApiProvider,
  testApiProvider,
  getApiProviderUsage,
  ApiError,
} from "../lib/api";
import type { ApiProvider } from "../types";
import {
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  SecretInput,
  Spinner,
  relativeTime,
} from "../components/common";

const KNOWN_KINDS = [
  { value: "openai_compatible", label: "OpenAI-compatible transcription" },
  { value: "generic_rest_transcription", label: "Generic REST transcription" },
];

interface FormState {
  name: string;
  adapter_key: "openai_compatible" | "generic_rest_transcription";
  base_url: string;
  endpoint_path: string;
  model_name: string;
  auth_type: "bearer" | "api_key" | "none";
  api_key: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  adapter_key: "openai_compatible",
  base_url: "",
  endpoint_path: "/audio/transcriptions",
  model_name: "",
  auth_type: "bearer",
  api_key: "",
};

export function ProvidersPage(): ReactElement {
  const queryClient = useQueryClient();
  const providersQuery = useQuery({
    queryKey: ["api-providers"],
    queryFn: listApiProviders,
  });
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [rotatingId, setRotatingId] = useState<string | null>(null);
  const [rotateSecret, setRotateSecret] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<ApiProvider | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, { ok: boolean; message: string }>
  >({});
  const [usageId, setUsageId] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createApiProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-providers"] });
      setShowForm(false);
      setForm(EMPTY_FORM);
      setFormError(null);
    },
    onError: (e) =>
      setFormError(
        e instanceof ApiError ? e.message : "Failed to create provider",
      ),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteApiProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-providers"] });
      setConfirmDelete(null);
      setActionError(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Delete failed"),
  });

  const actionMutation = useMutation({
    mutationFn: async (action: {
      id: string;
      kind: "enable" | "disable" | "default";
    }) => {
      if (action.kind === "enable") return enableApiProvider(action.id);
      if (action.kind === "disable") return disableApiProvider(action.id);
      return setDefaultApiProvider(action.id);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["api-providers"] }),
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Action failed"),
  });

  const rotateMutation = useMutation({
    mutationFn: ({ id, secret }: { id: string; secret: string }) =>
      rotateApiProviderSecret(id, secret),
    onSuccess: () => {
      setRotatingId(null);
      setRotateSecret("");
      queryClient.invalidateQueries({ queryKey: ["api-providers"] });
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Rotate failed"),
  });

  async function runTest(id: string): Promise<void> {
    setTestingId(id);
    setActionError(null);
    try {
      const result = await testApiProvider(id);
      setTestResults((prev) => ({
        ...prev,
        [id]: {
          ok: !result.last_error,
          message: result.last_error ?? "Provider configuration is valid",
        },
      }));
      queryClient.invalidateQueries({ queryKey: ["api-providers"] });
    } catch (e) {
      const message =
        e instanceof ApiError ? e.message : "Provider test failed";
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, message } }));
    } finally {
      setTestingId(null);
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!form.name.trim()) {
      setFormError("Display name is required");
      return;
    }
    if (form.auth_type !== "none" && !form.api_key.trim()) {
      setFormError(
        "API secret is required unless authentication is set to none",
      );
      return;
    }
    setFormError(null);
    createMutation.mutate({
      adapter_key: form.adapter_key,
      name: form.name.trim(),
      category: "transcription",
      base_url: form.base_url.trim() || null,
      endpoint_path: form.endpoint_path.trim() || "/audio/transcriptions",
      model_name: form.model_name.trim() || null,
      auth_type: form.auth_type,
      headers: {},
      capabilities: {},
      timeout_seconds: 120,
      retry_limit: 2,
      api_key: form.auth_type === "none" ? null : form.api_key,
    });
  }

  if (providersQuery.isLoading)
    return <LoadingScreen message="Loading API providers…" />;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="API Providers"
        subtitle="Connect external transcription and language model providers. Secrets are encrypted at rest and never returned by the API."
        actions={
          <button
            type="button"
            className="button-primary"
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancel" : "Add provider"}
          </button>
        }
      />

      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}

      {showForm && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold">New API provider</h2>
          <form
            className="mt-4 grid gap-4 sm:grid-cols-2"
            onSubmit={handleSubmit}
          >
            <label className="field-label">
              Display label
              <input
                className="field-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="OpenAI Whisper"
                required
              />
            </label>
            <label className="field-label">
              Provider kind
              <select
                className="field-input"
                value={form.adapter_key}
                onChange={(e) =>
                  setForm({
                    ...form,
                    adapter_key: e.target.value as FormState["adapter_key"],
                  })
                }
              >
                {KNOWN_KINDS.map((kind) => (
                  <option key={kind.value} value={kind.value}>
                    {kind.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              Endpoint URL
              <input
                className="field-input"
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://api.example.com"
              />
            </label>
            <label className="field-label">
              Endpoint path (optional)
              <input
                className="field-input"
                value={form.endpoint_path}
                onChange={(e) =>
                  setForm({ ...form, endpoint_path: e.target.value })
                }
                placeholder="/v1/audio/transcriptions"
              />
            </label>
            <label className="field-label">
              Default model
              <input
                className="field-input"
                value={form.model_name}
                onChange={(e) =>
                  setForm({ ...form, model_name: e.target.value })
                }
                placeholder="whisper-1"
              />
            </label>
            <label className="field-label">
              Authentication
              <select
                className="field-input"
                value={form.auth_type}
                onChange={(e) =>
                  setForm({
                    ...form,
                    auth_type: e.target.value as FormState["auth_type"],
                  })
                }
              >
                <option value="bearer">Bearer token</option>
                <option value="api_key">X-API-Key header</option>
                <option value="none">No authentication</option>
              </select>
            </label>
            <label className="field-label sm:col-span-2">
              API secret
              <SecretInput
                value={form.api_key}
                onChange={(v) => setForm({ ...form, api_key: v })}
                placeholder="sk-…"
              />
              <span className="text-xs text-slate-500">
                Stored encrypted with AES-256-GCM. Never returned to the
                frontend.
              </span>
            </label>
            {formError && (
              <p className="sm:col-span-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {formError}
              </p>
            )}
            <div className="sm:col-span-2 flex gap-2">
              <button
                type="submit"
                className="button-primary"
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? <Spinner /> : "Create provider"}
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  setShowForm(false);
                  setForm(EMPTY_FORM);
                  setFormError(null);
                  setEditingId(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </article>
      )}

      {!providersQuery.data?.length && !showForm && (
        <EmptyState
          title="No API providers configured"
          hint="Add a provider to enable external transcription or post-processing tasks."
        />
      )}

      <div className="grid gap-3">
        {providersQuery.data?.map((provider) => (
          <article
            key={provider.id}
            className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm"
            data-testid="api-provider-row"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold text-ink">{provider.name}</h3>
                  {provider.is_default && (
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                      Default
                    </span>
                  )}
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      provider.enabled
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {provider.enabled ? "Enabled" : "Disabled"}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                    {provider.secret_configured
                      ? "Secret configured"
                      : "No secret"}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">
                  {provider.adapter_key.replaceAll("_", " ")} ·{" "}
                  {provider.base_url ?? "No URL"}
                  {provider.model_name && ` · ${provider.model_name}`}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Endpoint path: {provider.endpoint_path}
                </p>
                {provider.last_error && (
                  <p className="mt-1 text-xs text-rose-700">
                    Last error: {provider.last_error}
                  </p>
                )}
                <p className="mt-1 text-xs text-slate-500">
                  {provider.last_tested_at
                    ? `Last tested ${relativeTime(provider.last_tested_at)}`
                    : "Not tested yet"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => runTest(provider.id)}
                  disabled={testingId === provider.id}
                >
                  {testingId === provider.id ? <Spinner /> : "Test"}
                </button>
                {provider.enabled ? (
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() =>
                      actionMutation.mutate({
                        id: provider.id,
                        kind: "disable",
                      })
                    }
                  >
                    Disable
                  </button>
                ) : (
                  <button
                    type="button"
                    className="button-primary"
                    onClick={() =>
                      actionMutation.mutate({ id: provider.id, kind: "enable" })
                    }
                  >
                    Enable
                  </button>
                )}
                {!provider.is_default && provider.enabled && (
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() =>
                      actionMutation.mutate({
                        id: provider.id,
                        kind: "default",
                      })
                    }
                  >
                    Make default
                  </button>
                )}
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => {
                    setRotatingId(provider.id);
                    setRotateSecret("");
                  }}
                >
                  Rotate secret
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() =>
                    setUsageId(usageId === provider.id ? null : provider.id)
                  }
                >
                  {usageId === provider.id ? "Hide usage" : "Usage"}
                </button>
                <button
                  type="button"
                  className="button-secondary !text-rose-700"
                  onClick={() => setConfirmDelete(provider)}
                >
                  Delete
                </button>
              </div>
            </div>

            {testResults[provider.id] && (
              <div
                className={`mt-3 rounded-lg px-3 py-2 text-xs ${
                  testResults[provider.id].ok
                    ? "bg-emerald-50 text-emerald-800"
                    : "bg-rose-50 text-rose-700"
                }`}
              >
                Test {testResults[provider.id].ok ? "succeeded" : "failed"}:{" "}
                {testResults[provider.id].message}
              </div>
            )}

            {rotatingId === provider.id && (
              <form
                className="mt-3 flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!rotateSecret.trim()) return;
                  rotateMutation.mutate({
                    id: provider.id,
                    secret: rotateSecret.trim(),
                  });
                }}
              >
                <label className="field-label flex-1 min-w-[200px]">
                  New secret
                  <SecretInput
                    value={rotateSecret}
                    onChange={setRotateSecret}
                    placeholder="New API key"
                  />
                </label>
                <button
                  type="submit"
                  className="button-primary"
                  disabled={rotateMutation.isPending || !rotateSecret.trim()}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => setRotatingId(null)}
                >
                  Cancel
                </button>
              </form>
            )}

            {usageId === provider.id && (
              <ProviderUsage providerId={provider.id} />
            )}
          </article>
        ))}
      </div>

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Delete API provider?"
        message={`${confirmDelete?.name ?? ""} will be removed and cannot be recovered. Future jobs will not be able to use this provider.`}
        destructive
        confirmLabel="Delete"
        onConfirm={() =>
          confirmDelete && deleteMutation.mutate(confirmDelete.id)
        }
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  );
}

function ProviderUsage({ providerId }: { providerId: string }): ReactElement {
  const query = useQuery({
    queryKey: ["api-provider-usage", providerId],
    queryFn: () => getApiProviderUsage(providerId),
  });
  if (query.isLoading)
    return <p className="mt-3 text-sm text-slate-500">Loading usage…</p>;
  if (query.isError || !query.data) {
    return <ErrorBanner message="Usage data is unavailable." />;
  }
  const usage = query.data;
  return (
    <div className="mt-3 grid gap-3 rounded-lg bg-slate-50 p-3 sm:grid-cols-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Total calls
        </p>
        <p className="mt-1 text-lg font-bold">{usage.total_calls}</p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Successful
        </p>
        <p className="mt-1 text-lg font-bold text-emerald-700">
          {usage.successful_calls}
        </p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Failed
        </p>
        <p className="mt-1 text-lg font-bold text-rose-700">
          {usage.failed_calls}
        </p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Estimated cost
        </p>
        <p className="mt-1 text-lg font-bold">
          ${usage.estimated_cost_usd.toFixed(4)}
        </p>
      </div>
      {usage.recent_calls.length > 0 && (
        <div className="sm:col-span-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recent calls
          </p>
          <ul className="mt-2 space-y-1 text-xs text-slate-700">
            {usage.recent_calls.slice(0, 5).map((call) => (
              <li key={call.id}>
                {call.task} · {call.status} ·{" "}
                {call.duration_ms ? `${call.duration_ms} ms` : "—"} ·{" "}
                {relativeTime(call.created_at)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
