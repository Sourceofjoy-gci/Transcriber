import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  getHardwareCapabilities,
  getStructuredSettings,
  listInstalledModels,
  putStructuredSettings,
  putTaskDefault,
} from "../lib/api";
import type { InstalledModel, StructuredSettings } from "../types";
import {
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";

export function SettingsPage(): ReactElement {
  const queryClient = useQueryClient();
  const structuredQuery = useQuery({
    queryKey: ["settings", "structured"],
    queryFn: getStructuredSettings,
  });
  const hardwareQuery = useQuery({
    queryKey: ["hardware"],
    queryFn: getHardwareCapabilities,
    retry: false,
  });
  const installedModelsQuery = useQuery({
    queryKey: ["installed-models"],
    queryFn: listInstalledModels,
    retry: false,
  });

  const [settingsForm, setSettingsForm] = useState<StructuredSettings | null>(
    null,
  );
  const [selectedDefaultModelId, setSelectedDefaultModelId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (structuredQuery.data) setSettingsForm(structuredQuery.data);
  }, [structuredQuery.data]);

  const structuredMutation = useMutation({
    mutationFn: putStructuredSettings,
    onSuccess: (data) => {
      setSettingsForm(data);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setActionError(null);
    },
    onError: (error) =>
      setActionError(
        error instanceof ApiError ? error.message : "Failed to save settings",
      ),
  });
  const defaultMutation = useMutation({
    mutationFn: putTaskDefault,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["installed-models"] });
      setActionError(null);
    },
    onError: (error) =>
      setActionError(
        error instanceof ApiError
          ? error.message
          : "Failed to save default model",
      ),
  });

  if (structuredQuery.isLoading || !settingsForm)
    return <LoadingScreen message="Loading settings..." />;

  const installedModels = installedModelsQuery.data ?? [];
  const enabledModels = installedModels.filter(isSelectableDefaultModel);
  const currentDefault = installedModels.find((model) => model.is_default);
  const defaultModelId = selectedDefaultModelId || currentDefault?.id || "";

  function saveSettings(): void {
    if (!settingsForm) return;
    structuredMutation.mutate({
      organisation: {
        retention_days: numberOrNull(settingsForm.organisation.retention_days),
        external_apis_allowed: Boolean(
          settingsForm.organisation.external_apis_allowed,
        ),
        local_only_enforced: Boolean(
          settingsForm.organisation.local_only_enforced,
        ),
      },
      upload: settingsForm.upload,
      queue: settingsForm.queue,
      ai: settingsForm.ai,
    });
  }

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Settings"
        subtitle="Structured workspace policy and runtime defaults."
      />
      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Organisation policy</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <label className="field-label">
            Retention days
            <input
              className="field-input"
              inputMode="numeric"
              value={settingsForm.organisation.retention_days ?? ""}
              onChange={(event) =>
                setSettingsForm({
                  ...settingsForm,
                  organisation: {
                    ...settingsForm.organisation,
                    retention_days: numberOrNull(event.target.value),
                  },
                })
              }
            />
          </label>
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={settingsForm.organisation.local_only_enforced}
              onChange={(event) =>
                setSettingsForm({
                  ...settingsForm,
                  organisation: {
                    ...settingsForm.organisation,
                    local_only_enforced: event.target.checked,
                  },
                })
              }
            />
            Enforce local-only processing
          </label>
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={settingsForm.organisation.external_apis_allowed}
              onChange={(event) =>
                setSettingsForm({
                  ...settingsForm,
                  organisation: {
                    ...settingsForm.organisation,
                    external_apis_allowed: event.target.checked,
                  },
                })
              }
            />
            Allow external APIs
          </label>
        </div>
      </article>

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Upload limits</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <NumberSetting
            label="Maximum upload bytes"
            value={settingsForm.upload.max_upload_bytes}
            onChange={(value) =>
              setSettingsForm({
                ...settingsForm,
                upload: { ...settingsForm.upload, max_upload_bytes: value },
              })
            }
          />
        </div>
      </article>

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Queue defaults</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <NumberSetting
            label="Max concurrent jobs"
            value={settingsForm.queue.max_concurrent_jobs}
            onChange={(value) =>
              setSettingsForm({
                ...settingsForm,
                queue: { ...settingsForm.queue, max_concurrent_jobs: value },
              })
            }
          />
          <label className="field-label md:col-span-2">
            Default report template kind
            <input
              className="field-input"
              value={String(settingsForm.ai.default_report_template_kind ?? "")}
              onChange={(event) =>
                setSettingsForm({
                  ...settingsForm,
                  ai: {
                    ...settingsForm.ai,
                    default_report_template_kind: event.target.value,
                  },
                })
              }
            />
          </label>
        </div>
        <button
          type="button"
          className="button-primary mt-4"
          onClick={saveSettings}
          disabled={structuredMutation.isPending}
        >
          {structuredMutation.isPending ? <Spinner /> : "Save settings"}
        </button>
      </article>

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Default transcription model</h2>
        {installedModelsQuery.isLoading ? (
          <p className="mt-2 text-sm text-slate-500">
            Loading installed models...
          </p>
        ) : enabledModels.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">
            No installed and enabled local models are available.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
            <label className="field-label">
              Installed model
              <select
                className="field-input"
                value={defaultModelId}
                onChange={(event) =>
                  setSelectedDefaultModelId(event.target.value)
                }
              >
                {enabledModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.catalog.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="button"
                className="button-primary"
                disabled={!defaultModelId || defaultMutation.isPending}
                onClick={() =>
                  defaultModelId && defaultMutation.mutate(defaultModelId)
                }
              >
                {defaultMutation.isPending ? <Spinner /> : "Save default"}
              </button>
            </div>
            {currentDefault && (
              <p className="text-sm text-slate-600 lg:col-span-2">
                Current default: {currentDefault.catalog.name}
              </p>
            )}
          </div>
        )}
      </article>

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Hardware capabilities</h2>
        {hardwareQuery.isError ? (
          <ErrorBanner message="Hardware information is unavailable." />
        ) : hardwareQuery.isLoading ? (
          <p className="mt-2 text-sm text-slate-500">Detecting hardware...</p>
        ) : hardwareQuery.data ? (
          <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <HardwareStat
              label="CPU cores"
              value={String(hardwareQuery.data.cpu_cores)}
            />
            <HardwareStat
              label="Total memory"
              value={`${(hardwareQuery.data.total_memory_bytes / 1024 ** 3).toFixed(1)} GB`}
            />
            <HardwareStat
              label="CUDA available"
              value={hardwareQuery.data.has_cuda ? "Yes" : "No"}
            />
            <HardwareStat
              label="Detected GPUs"
              value={
                hardwareQuery.data.detected_gpus
                  .map((gpu) => gpu.name)
                  .join(", ") || "None"
              }
            />
          </dl>
        ) : null}
      </article>
    </section>
  );
}

function NumberSetting({
  label,
  value,
  onChange,
}: {
  label: string;
  value: unknown;
  onChange: (value: number | null) => void;
}): ReactElement {
  return (
    <label className="field-label">
      {label}
      <input
        className="field-input"
        inputMode="numeric"
        value={value == null ? "" : String(value)}
        onChange={(event) => onChange(numberOrNull(event.target.value))}
      />
    </label>
  );
}

function HardwareStat({
  label,
  value,
}: {
  label: string;
  value: string;
}): ReactElement {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-1 text-base font-bold text-ink">{value}</dd>
    </div>
  );
}

function isSelectableDefaultModel(model: InstalledModel): boolean {
  return (
    model.status === "installed" &&
    model.enabled &&
    model.hardware_compatibility?.compatible !== false
  );
}

function numberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
