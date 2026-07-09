import { useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProject,
  deleteProject,
  listProjects,
  updateProject,
} from "../lib/api";
import {
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";
import type { ProjectInput } from "../types";

const emptyProject: ProjectInput = {
  name: "New Project",
  description: "",
  sensitivity: "standard",
  retention_days: null,
  external_apis_allowed: null,
};

export function ProjectsPage(): ReactElement {
  const queryClient = useQueryClient();
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });
  const [form, setForm] = useState<ProjectInput>(emptyProject);
  const [actionError, setActionError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setForm(emptyProject);
    },
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Project save failed",
      ),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<ProjectInput> }) =>
      updateProject(id, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Project update failed",
      ),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Project archive failed",
      ),
  });

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    createMutation.mutate(normalizeProject(form));
  }

  if (projectsQuery.isLoading)
    return <LoadingScreen message="Loading projects..." />;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Projects"
        subtitle="Organise media, retention, and API policy by project."
      />
      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}
      <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-ink">Create project</h2>
        <form
          className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5"
          onSubmit={submit}
        >
          <label className="field-label lg:col-span-2">
            Name
            <input
              className="field-input"
              value={form.name}
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
            />
          </label>
          <label className="field-label">
            Sensitivity
            <select
              className="field-input"
              value={form.sensitivity}
              onChange={(event) =>
                setForm({
                  ...form,
                  sensitivity: event.target
                    .value as ProjectInput["sensitivity"],
                })
              }
            >
              <option value="standard">Standard</option>
              <option value="sensitive">Sensitive</option>
              <option value="restricted">Restricted</option>
            </select>
          </label>
          <label className="field-label">
            Retention days
            <input
              className="field-input"
              inputMode="numeric"
              value={form.retention_days ?? ""}
              onChange={(event) =>
                setForm({
                  ...form,
                  retention_days: numberOrNull(event.target.value),
                })
              }
            />
          </label>
          <label className="field-label">
            External APIs
            <select
              className="field-input"
              value={String(form.external_apis_allowed ?? "")}
              onChange={(event) =>
                setForm({
                  ...form,
                  external_apis_allowed:
                    event.target.value === ""
                      ? null
                      : event.target.value === "true",
                })
              }
            >
              <option value="">Use organisation policy</option>
              <option value="true">Allowed</option>
              <option value="false">Blocked</option>
            </select>
          </label>
          <button
            type="submit"
            className="button-primary md:col-span-2 lg:col-span-5"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? <Spinner /> : "Save project"}
          </button>
        </form>
      </article>
      <div className="grid gap-3">
        {(projectsQuery.data ?? []).map((project) => (
          <article
            key={project.id}
            className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-ink">{project.name}</h2>
                <p className="mt-1 text-sm text-slate-600">
                  {project.sensitivity} ·{" "}
                  {project.retention_days
                    ? `${project.retention_days} day retention`
                    : "Org retention"}{" "}
                  ·{" "}
                  {project.external_apis_allowed === null
                    ? "Org API policy"
                    : project.external_apis_allowed
                      ? "API allowed"
                      : "API blocked"}
                </p>
                {project.description && (
                  <p className="mt-2 text-sm text-slate-600">
                    {project.description}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() =>
                    updateMutation.mutate({
                      id: project.id,
                      patch: { sensitivity: "restricted" },
                    })
                  }
                >
                  Restrict
                </button>
                <button
                  type="button"
                  className="button-secondary !text-rose-700"
                  onClick={() => deleteMutation.mutate(project.id)}
                >
                  Archive
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function normalizeProject(project: ProjectInput): ProjectInput {
  return { ...project, description: project.description || null };
}

function numberOrNull(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
