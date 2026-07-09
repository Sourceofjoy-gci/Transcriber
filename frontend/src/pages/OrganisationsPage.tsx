import { useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createOrganisation,
  listOrganisations,
  setActiveOrganisationId,
  updateOrganisation,
} from "../lib/api";
import {
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";

export function OrganisationsPage(): ReactElement {
  const queryClient = useQueryClient();
  const organisationsQuery = useQuery({
    queryKey: ["organisations"],
    queryFn: listOrganisations,
  });
  const [name, setName] = useState("New Organisation");
  const [actionError, setActionError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createOrganisation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organisations"] });
      setName("New Organisation");
    },
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Organisation create failed",
      ),
  });
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      retention_days,
    }: {
      id: string;
      retention_days: number | null;
    }) => updateOrganisation(id, { retention_days }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["organisations"] }),
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Organisation update failed",
      ),
  });

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    createMutation.mutate({ name, local_only_enforced: true });
  }

  if (organisationsQuery.isLoading)
    return <LoadingScreen message="Loading organisations..." />;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Organisations"
        subtitle="Switch workspaces and manage organisation policy."
      />
      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}
      <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-ink">
          Create organisation
        </h2>
        <form className="mt-4 flex flex-wrap gap-3" onSubmit={submit}>
          <input
            className="field-input min-w-64"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button
            type="submit"
            className="button-primary"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? <Spinner /> : "Create organisation"}
          </button>
        </form>
      </article>
      <div className="grid gap-3">
        {(organisationsQuery.data ?? []).map((organisation) => (
          <article
            key={organisation.id}
            className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-ink">{organisation.name}</h2>
                <p className="mt-1 text-sm text-slate-600">
                  {organisation.slug} ·{" "}
                  {organisation.role_code?.replaceAll("_", " ") ?? "member"} ·{" "}
                  {organisation.local_only_enforced
                    ? "local only"
                    : "external APIs configurable"}
                </p>
                {organisation.is_current && (
                  <span className="mt-2 inline-flex rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                    Current
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => {
                    setActiveOrganisationId(organisation.id);
                    queryClient.invalidateQueries();
                  }}
                >
                  Switch
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() =>
                    updateMutation.mutate({
                      id: organisation.id,
                      retention_days: 90,
                    })
                  }
                >
                  90 day retention
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
