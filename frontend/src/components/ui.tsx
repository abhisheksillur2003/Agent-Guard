import clsx from "clsx";
import type { LucideIcon } from "lucide-react";

import { titleCase } from "@/lib/format";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-action">{action}</div>}
    </header>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "blue",
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: LucideIcon;
  tone?: "blue" | "green" | "red" | "amber";
}) {
  return (
    <article className="metric-card">
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{hint}</span>
      </div>
      <span className={clsx("metric-icon", `metric-${tone}`)}>
        <Icon size={20} />
      </span>
    </article>
  );
}

export function StatusPill({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone = ["active", "succeeded", "approved", "allow", "low"].includes(
    normalized,
  )
    ? "success"
    : ["pending", "running", "require_approval", "medium", "record"].includes(
          normalized,
        )
      ? "warning"
      : [
            "failed",
            "denied",
            "deny",
            "rejected",
            "critical",
            "revoked",
          ].includes(normalized)
        ? "danger"
        : normalized === "high" ||
            normalized === "timed_out" ||
            normalized === "suspended"
          ? "high"
          : "neutral";
  return (
    <span className={clsx("status-pill", `status-${tone}`)}>
      {titleCase(value)}
    </span>
  );
}

export function Panel({
  title,
  subtitle,
  children,
  className,
  action,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}) {
  return (
    <section className={clsx("panel", className)}>
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function LoadingState({
  label = "Loading secure data",
}: {
  label?: string;
}) {
  return (
    <div className="state-card" role="status">
      <span className="spinner" />
      <p>{label}…</p>
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="state-card state-error">
      <strong>Unable to load this view</strong>
      <p>{error.message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  );
}
