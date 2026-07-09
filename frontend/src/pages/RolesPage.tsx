import { useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createRole,
  deleteRole,
  listPermissions,
  listRoles,
  updateRole,
} from "../lib/api";
import {
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";

export function RolesPage(): ReactElement {
  const queryClient = useQueryClient();
  const rolesQuery = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const permissionsQuery = useQuery({
    queryKey: ["permissions"],
    queryFn: listPermissions,
  });
  const [code, setCode] = useState("custom_role");
  const [name, setName] = useState("Custom Role");
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([
    "assets.read",
  ]);
  const [actionError, setActionError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createRole,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roles"] }),
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Role create failed",
      ),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, permissions }: { id: string; permissions: string[] }) =>
      updateRole(id, { permission_codes: permissions }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roles"] }),
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Role update failed",
      ),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteRole,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roles"] }),
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Role delete failed",
      ),
  });

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    createMutation.mutate({
      code,
      name,
      permission_codes: selectedPermissions,
    });
  }

  if (rolesQuery.isLoading || permissionsQuery.isLoading)
    return <LoadingScreen message="Loading roles..." />;

  const permissions = permissionsQuery.data ?? [];

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Roles"
        subtitle="Create custom roles and assign permissions."
      />
      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}
      <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-ink">Create role</h2>
        <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={submit}>
          <label className="field-label">
            Code
            <input
              className="field-input"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <label className="field-label">
            Name
            <input
              className="field-input"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div className="md:col-span-2 flex flex-wrap gap-2">
            {permissions.map((permission) => (
              <label
                key={permission.id}
                className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
              >
                <input
                  type="checkbox"
                  className="mr-2"
                  checked={selectedPermissions.includes(permission.code)}
                  onChange={(event) =>
                    setSelectedPermissions((current) =>
                      event.target.checked
                        ? [...current, permission.code]
                        : current.filter(
                            (codeValue) => codeValue !== permission.code,
                          ),
                    )
                  }
                />
                {permission.code}
              </label>
            ))}
          </div>
          <button
            type="submit"
            className="button-primary md:col-span-2"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? <Spinner /> : "Create role"}
          </button>
        </form>
      </article>
      <div className="grid gap-3">
        {(rolesQuery.data ?? []).map((role) => (
          <article
            key={role.id}
            className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-ink">{role.name}</h2>
                <p className="mt-1 text-sm text-slate-600">{role.code}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {role.permissions.map((permission) => (
                    <span
                      key={permission}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                    >
                      {permission}
                    </span>
                  ))}
                </div>
              </div>
              {!role.is_system && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() =>
                      updateMutation.mutate({
                        id: role.id,
                        permissions: selectedPermissions,
                      })
                    }
                  >
                    Apply permissions
                  </button>
                  <button
                    type="button"
                    className="button-secondary !text-rose-700"
                    onClick={() => deleteMutation.mutate(role.id)}
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
