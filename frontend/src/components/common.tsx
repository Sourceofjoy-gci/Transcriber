import type { ReactElement, ReactNode } from "react";

export function LoadingScreen({
  message = "Loading…",
}: {
  message?: string;
}): ReactElement {
  return (
    <main className="grid min-h-[60vh] place-items-center text-sm font-medium text-slate-600">
      {message}
    </main>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: string;
}): ReactElement {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p className="text-base font-semibold text-ink">{title}</p>
      {hint && <p className="mt-2 text-sm text-slate-500">{hint}</p>}
    </div>
  );
}

export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="button-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}): ReactElement {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Info({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}): ReactElement {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-medium text-ink">{value}</p>
    </div>
  );
}

export function formatBytes(value: number): string {
  if (!value || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unit = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${(value / 1024 ** unit).toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDuration(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function formatTimestamp(ms: number): string {
  return formatDuration(ms / 1000);
}

export function estimateProcessingTime(fileSize: number): string {
  const minutes = Math.max(1, Math.ceil(fileSize / (40 * 1024 * 1024)));
  return `About ${minutes}–${minutes * 3} min`;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  destructive = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}): ReactElement | null {
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-bold text-ink">{title}</h2>
        <p className="mt-2 text-sm text-slate-600">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="button-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={
              destructive
                ? "button-primary !bg-rose-600 hover:!bg-rose-700"
                : "button-primary"
            }
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Spinner(): ReactElement {
  return (
    <span
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
      aria-hidden="true"
    />
  );
}

export function SecretInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}): ReactElement {
  return (
    <input
      type="password"
      className="field-input font-mono"
      autoComplete="off"
      spellCheck={false}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
