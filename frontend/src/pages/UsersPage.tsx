import { useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  createUser,
  deleteUser,
  listMemberships,
  listRoles,
  listUsers,
  updateUser,
} from "../lib/api";
import type { User } from "../types";
import {
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
  relativeTime,
} from "../components/common";

interface CreateFormState {
  email: string;
  display_name: string;
  password: string;
  role_code: string;
}

const EMPTY_CREATE: CreateFormState = {
  email: "",
  display_name: "",
  password: "",
  role_code: "",
};

export function UsersPage(): ReactElement {
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const rolesQuery = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const membershipsQuery = useQuery({
    queryKey: ["memberships"],
    queryFn: listMemberships,
  });

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateFormState>(EMPTY_CREATE);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<User | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState<string>("");

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["memberships"] });
      setShowForm(false);
      setForm(EMPTY_CREATE);
      setFormError(null);
    },
    onError: (e) =>
      setFormError(e instanceof ApiError ? e.message : "Failed to create user"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["memberships"] });
      setConfirmDelete(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Delete failed"),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: Parameters<typeof updateUser>[1];
    }) => updateUser(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["memberships"] });
      setEditingId(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Update failed"),
  });

  function handleSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (
      !form.email ||
      !form.display_name ||
      !form.password ||
      !form.role_code
    ) {
      setFormError("All fields are required");
      return;
    }
    if (form.password.length < 12) {
      setFormError("Password must be at least 12 characters");
      return;
    }
    setFormError(null);
    createMutation.mutate(form);
  }

  if (usersQuery.isLoading) return <LoadingScreen message="Loading users…" />;

  const users = usersQuery.data ?? [];
  const memberships = membershipsQuery.data ?? [];
  const roleById = new Map(
    rolesQuery.data?.map((role) => [role.code, role.name] as const) ?? [],
  );
  const userById = new Map(users.map((user) => [user.id, user] as const));

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Users & Roles"
        subtitle="Manage workspace membership, role assignments, and account status."
        actions={
          <button
            type="button"
            className="button-primary"
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancel" : "Invite user"}
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
          <h2 className="text-lg font-bold">Invite a new user</h2>
          <form
            className="mt-4 grid gap-4 sm:grid-cols-2"
            onSubmit={handleSubmit}
          >
            <label className="field-label">
              Email address
              <input
                type="email"
                className="field-input"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </label>
            <label className="field-label">
              Display name
              <input
                className="field-input"
                value={form.display_name}
                onChange={(e) =>
                  setForm({ ...form, display_name: e.target.value })
                }
                required
              />
            </label>
            <label className="field-label">
              Initial role
              <select
                className="field-input"
                value={form.role_code}
                onChange={(e) =>
                  setForm({ ...form, role_code: e.target.value })
                }
                required
              >
                <option value="">Select a role…</option>
                {rolesQuery.data?.map((role) => (
                  <option key={role.code} value={role.code}>
                    {role.name}
                  </option>
                ))}
              </select>
              {form.role_code && roleById.get(form.role_code) && (
                <span className="text-xs text-slate-500">
                  {(
                    rolesQuery.data?.find((r) => r.code === form.role_code)
                      ?.permissions ?? []
                  )
                    .slice(0, 4)
                    .join(", ")}
                </span>
              )}
            </label>
            <label className="field-label">
              Initial password (must be ≥ 12 chars)
              <input
                type="password"
                className="field-input"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                minLength={12}
                required
              />
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
                {createMutation.isPending ? <Spinner /> : "Create user"}
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  setShowForm(false);
                  setForm(EMPTY_CREATE);
                  setFormError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </article>
      )}

      {!users.length && !showForm && (
        <EmptyState
          title="No users yet"
          hint="Invite users to your workspace."
        />
      )}

      <div className="overflow-hidden rounded-2xl border border-emerald-950/10 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const membership = memberships.find((m) => m.user_id === user.id);
              return (
                <tr
                  key={user.id}
                  className="border-t border-slate-100 align-top"
                >
                  <td className="px-4 py-3 font-medium">{user.display_name}</td>
                  <td className="px-4 py-3 text-slate-600">{user.email}</td>
                  <td className="px-4 py-3">
                    {editingId === user.id ? (
                      <select
                        className="field-input"
                        value={editRole}
                        onChange={(e) => setEditRole(e.target.value)}
                      >
                        {rolesQuery.data?.map((role) => (
                          <option key={role.code} value={role.code}>
                            {role.name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-xs">
                        {membership
                          ? (roleById.get(membership.role_code) ??
                            membership.role_code)
                          : "—"}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        user.is_active
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {user.is_active ? "Active" : "Disabled"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      {editingId === user.id ? (
                        <>
                          <button
                            type="button"
                            className="button-primary"
                            disabled={updateMutation.isPending}
                            onClick={() =>
                              updateMutation.mutate({
                                id: user.id,
                                patch: { role_code: editRole },
                              })
                            }
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            className="button-secondary"
                            onClick={() => setEditingId(null)}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="button-secondary"
                            onClick={() => {
                              setEditingId(user.id);
                              setEditRole(membership?.role_code ?? "");
                            }}
                          >
                            Edit role
                          </button>
                          <button
                            type="button"
                            className="button-secondary"
                            onClick={() =>
                              updateMutation.mutate({
                                id: user.id,
                                patch: { is_active: !user.is_active },
                              })
                            }
                          >
                            {user.is_active ? "Disable" : "Enable"}
                          </button>
                          <button
                            type="button"
                            className="button-secondary !text-rose-700"
                            onClick={() => setConfirmDelete(user)}
                          >
                            Remove
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {memberships.length > 0 && (
        <div>
          <h2 className="text-lg font-bold">Recent membership activity</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">
            {memberships.slice(0, 5).map((m) => {
              const user = userById.get(m.user_id);
              return (
                <li key={m.id}>
                  {user ? `${user.display_name} (${user.email})` : m.user_id} ·{" "}
                  {roleById.get(m.role_code) ?? m.role_code} · joined{" "}
                  {relativeTime(m.created_at)}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Remove user?"
        message={`${confirmDelete?.display_name ?? ""} will lose access to this workspace. The user record can be re-invited later.`}
        destructive
        confirmLabel="Remove"
        onConfirm={() =>
          confirmDelete && deleteMutation.mutate(confirmDelete.id)
        }
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  );
}
