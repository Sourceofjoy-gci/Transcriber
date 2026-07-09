import { useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  addInstalledModel,
  cancelInstalledModelDownload,
  createModelCatalogEntry,
  deleteInstalledModel,
  disableInstalledModel,
  downloadInstalledModel,
  enableInstalledModel,
  listInstalledModels,
  listModelCatalog,
  putTaskDefault,
  testInstalledModel,
} from "../lib/api";
import type {
  InstalledModel,
  ModelCatalogInput,
  ModelTestResult,
} from "../types";
import {
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  formatBytes,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";

export function ModelsPage(): ReactElement {
  const queryClient = useQueryClient();
  const catalogQuery = useQuery({
    queryKey: ["model-catalog"],
    queryFn: listModelCatalog,
  });
  const installedQuery = useQuery({
    queryKey: ["installed-models"],
    queryFn: listInstalledModels,
    refetchInterval: 3000,
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, { ok: boolean; message: string }>
  >({});
  const [testingId, setTestingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<InstalledModel | null>(
    null,
  );
  const [customModel, setCustomModel] = useState({
    adapter_key: "whisper_cpp",
    name: "",
    model_identifier: "",
    source_url: "",
    checksum: "",
  });

  const installMutation = useMutation({
    mutationFn: addInstalledModel,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["installed-models"] }),
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Add failed"),
  });
  const downloadMutation = useMutation({
    mutationFn: downloadInstalledModel,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["installed-models"] }),
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Download failed"),
  });
  const cancelMutation = useMutation({
    mutationFn: cancelInstalledModelDownload,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["installed-models"] }),
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Cancel failed"),
  });
  const enableMutation = useMutation({
    mutationFn: enableInstalledModel,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["installed-models"] }),
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Enable failed"),
  });
  const disableMutation = useMutation({
    mutationFn: disableInstalledModel,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["installed-models"] }),
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Disable failed"),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteInstalledModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["installed-models"] });
      setConfirmDelete(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Delete failed"),
  });
  const defaultMutation = useMutation({
    mutationFn: putTaskDefault,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["installed-models"] }),
    onError: (e) =>
      setActionError(
        e instanceof ApiError ? e.message : "Default update failed",
      ),
  });
  const customCatalogMutation = useMutation({
    mutationFn: createModelCatalogEntry,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["model-catalog"] });
      setCustomModel({
        adapter_key: "whisper_cpp",
        name: "",
        model_identifier: "",
        source_url: "",
        checksum: "",
      });
    },
    onError: (e) =>
      setActionError(
        e instanceof ApiError ? e.message : "Catalog entry failed",
      ),
  });

  async function runTest(id: string): Promise<void> {
    setTestingId(id);
    setActionError(null);
    try {
      const result = await testInstalledModel(id);
      setTestResults((prev) => ({
        ...prev,
        [id]: normaliseTestResult(result),
      }));
      queryClient.invalidateQueries({ queryKey: ["installed-models"] });
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Model test failed";
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, message } }));
    } finally {
      setTestingId(null);
    }
  }

  function submitCustomModel(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!customModel.name.trim() || !customModel.model_identifier.trim()) {
      setActionError("Custom models require a name and identifier");
      return;
    }
    const payload: ModelCatalogInput = {
      adapter_key: customModel.adapter_key,
      name: customModel.name.trim(),
      model_identifier: customModel.model_identifier.trim(),
      model_type: "transcription",
      source_url: customModel.source_url.trim() || null,
      checksum: customModel.checksum.trim() || null,
      requirements: {
        recommended_device:
          customModel.adapter_key === "whisper_cpp" ? "cpu" : "cpu_or_cuda",
      },
      capabilities: {
        tasks: ["transcription"],
        word_timestamps: customModel.adapter_key !== "whisper_cpp",
      },
    };
    setActionError(null);
    customCatalogMutation.mutate(payload);
  }

  if (catalogQuery.isLoading)
    return <LoadingScreen message="Loading model catalog…" />;

  const installed = installedQuery.data ?? [];
  const installedByCatalog = new Map(
    installed.map((item) => [item.catalog_id, item] as const),
  );

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Model Manager"
        subtitle="Download, test, enable, and manage local transcription models. Models remain on this deployment."
      />

      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-ink">Add custom model</h2>
        <form
          className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5"
          onSubmit={submitCustomModel}
        >
          <label className="field-label">
            Adapter
            <select
              name="custom-adapter"
              className="field-input"
              value={customModel.adapter_key}
              onChange={(event) =>
                setCustomModel((prev) => ({
                  ...prev,
                  adapter_key: event.target.value,
                }))
              }
            >
              <option value="whisper_cpp">whisper cpp</option>
              <option value="faster_whisper">faster whisper</option>
              <option value="whisper_local">whisper local</option>
            </select>
          </label>
          <label className="field-label">
            Name
            <input
              name="custom-name"
              className="field-input"
              value={customModel.name}
              onChange={(event) =>
                setCustomModel((prev) => ({
                  ...prev,
                  name: event.target.value,
                }))
              }
              placeholder="Custom Legal Model"
            />
          </label>
          <label className="field-label">
            Identifier
            <input
              name="custom-identifier"
              className="field-input"
              value={customModel.model_identifier}
              onChange={(event) =>
                setCustomModel((prev) => ({
                  ...prev,
                  model_identifier: event.target.value,
                }))
              }
              placeholder="custom/legal.bin"
            />
          </label>
          <label className="field-label">
            Source URL
            <input
              name="custom-source-url"
              className="field-input"
              value={customModel.source_url}
              onChange={(event) =>
                setCustomModel((prev) => ({
                  ...prev,
                  source_url: event.target.value,
                }))
              }
              placeholder="https://models.example.com/legal.bin"
            />
          </label>
          <label className="field-label">
            SHA-256
            <input
              name="custom-checksum"
              className="field-input"
              value={customModel.checksum}
              onChange={(event) =>
                setCustomModel((prev) => ({
                  ...prev,
                  checksum: event.target.value,
                }))
              }
              placeholder="sha256:..."
            />
          </label>
          <div className="md:col-span-2 xl:col-span-5">
            <button
              type="submit"
              className="button-primary"
              disabled={customCatalogMutation.isPending}
            >
              {customCatalogMutation.isPending ? (
                <Spinner />
              ) : (
                "Add custom model"
              )}
            </button>
          </div>
        </form>
      </article>

      {!catalogQuery.data?.length && (
        <EmptyState title="No models available in the catalog." />
      )}

      <div className="grid gap-3">
        {catalogQuery.data?.map((model) => {
          const installedItem = installedByCatalog.get(model.id);
          const incompatible = installedItem
            ? isIncompatible(installedItem)
            : false;
          return (
            <article
              key={model.id}
              className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm"
              data-testid="model-card"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-ink">{model.name}</h3>
                  <p className="mt-1 text-sm text-slate-600">
                    {model.adapter_key.replaceAll("_", " ")} ·{" "}
                    {model.model_type.replaceAll("_", " ")}
                    {model.size_bytes && ` · ${formatBytes(model.size_bytes)}`}
                  </p>
                  {model.capabilities && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {Object.entries(model.capabilities)
                        .slice(0, 4)
                        .map(([k, v]) => (
                          <span
                            key={k}
                            className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                          >
                            {k}: {String(v)}
                          </span>
                        ))}
                    </div>
                  )}
                  {installedItem?.is_default && (
                    <span className="mt-2 inline-flex rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                      Default
                    </span>
                  )}
                  {installedItem?.last_error && (
                    <p className="mt-2 text-xs text-rose-700">
                      {installedItem.last_error}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {!installedItem && (
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => installMutation.mutate(model.id)}
                      disabled={installMutation.isPending}
                    >
                      Add
                    </button>
                  )}
                  {installedItem?.status === "available" && (
                    <button
                      type="button"
                      className="button-primary"
                      onClick={() => downloadMutation.mutate(installedItem.id)}
                      disabled={downloadMutation.isPending}
                    >
                      Download
                    </button>
                  )}
                  {installedItem?.status === "downloading" && (
                    <>
                      <div className="flex items-center gap-2 text-sm">
                        <Spinner /> Downloading{" "}
                        {installedItem.download_progress}%
                      </div>
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() => cancelMutation.mutate(installedItem.id)}
                        disabled={cancelMutation.isPending}
                      >
                        Cancel
                      </button>
                    </>
                  )}
                  {installedItem && (
                    <>
                      {installedItem.status === "installed" &&
                        installedItem.enabled &&
                        !installedItem.is_default && (
                          <button
                            type="button"
                            className="button-secondary"
                            onClick={() =>
                              defaultMutation.mutate(installedItem.id)
                            }
                            disabled={defaultMutation.isPending || incompatible}
                          >
                            Set default
                          </button>
                        )}
                      {installedItem.enabled ? (
                        <button
                          type="button"
                          className="button-secondary"
                          onClick={() =>
                            disableMutation.mutate(installedItem.id)
                          }
                          disabled={installedItem.status !== "installed"}
                        >
                          Disable
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="button-primary"
                          onClick={() =>
                            enableMutation.mutate(installedItem.id)
                          }
                          disabled={installedItem.status !== "installed"}
                        >
                          Enable
                        </button>
                      )}
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() => runTest(installedItem.id)}
                        disabled={
                          testingId === installedItem.id ||
                          installedItem.status !== "installed"
                        }
                      >
                        {testingId === installedItem.id ? <Spinner /> : "Test"}
                      </button>
                      <button
                        type="button"
                        className="button-secondary !text-rose-700"
                        onClick={() => setConfirmDelete(installedItem)}
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
              {installedItem && (
                <div className="mt-3 grid gap-3 text-xs text-slate-600 sm:grid-cols-3">
                  <span>
                    <strong>Status:</strong> {installedItem.status}
                  </span>
                  <span>
                    <strong>Enabled:</strong>{" "}
                    {installedItem.enabled ? "yes" : "no"}
                  </span>
                  <span>
                    <strong>Progress:</strong> {installedItem.download_progress}
                    %
                  </span>
                </div>
              )}
              {installedItem && <CompatibilityDetails model={installedItem} />}
              {installedItem && testResults[installedItem.id] && (
                <div
                  className={`mt-2 rounded-lg px-3 py-2 text-xs ${
                    testResults[installedItem.id].ok
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-rose-50 text-rose-700"
                  }`}
                >
                  Test {testResults[installedItem.id].ok ? "passed" : "failed"}:{" "}
                  {testResults[installedItem.id].message}
                </div>
              )}
            </article>
          );
        })}
      </div>

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Delete model?"
        message={
          confirmDelete
            ? `${confirmDelete.catalog.name} will be removed from disk. You will need to download it again before it can be used.`
            : ""
        }
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

function CompatibilityDetails({
  model,
}: {
  model: InstalledModel;
}): ReactElement | null {
  const compatibility = model.hardware_compatibility ?? {};
  const reasons = stringList(compatibility.reasons);
  const recommendations = stringList(compatibility.recommendations);
  const labels = stringList(compatibility.worker_labels);
  if (
    !reasons.length &&
    !recommendations.length &&
    !labels.length &&
    compatibility.compatible === undefined
  ) {
    return null;
  }
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      {compatibility.compatible === false && (
        <span className="rounded-full bg-rose-50 px-2 py-0.5 font-semibold text-rose-700">
          Incompatible
        </span>
      )}
      {compatibility.compatible === true && (
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-800">
          Compatible
        </span>
      )}
      {reasons.map((reason) => (
        <span
          key={reason}
          className="rounded-full bg-rose-50 px-2 py-0.5 text-rose-700"
        >
          {reason}
        </span>
      ))}
      {recommendations.map((recommendation) => (
        <span
          key={recommendation}
          className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800"
        >
          {recommendation}
        </span>
      ))}
      {labels.map((label) => (
        <span
          key={label}
          className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-700"
        >
          worker: {label}
        </span>
      ))}
    </div>
  );
}

function isIncompatible(model: InstalledModel): boolean {
  return model.hardware_compatibility?.compatible === false;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function normaliseTestResult(result: ModelTestResult): {
  ok: boolean;
  message: string;
} {
  const ok = result.status === "ready" || result.probe.compatible === true;
  const reason = String(
    result.probe.reason ?? result.probe.recommendations ?? result.status,
  );
  return { ok, message: reason };
}
