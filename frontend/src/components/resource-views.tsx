"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Database,
  Gauge,
  Network,
  Server,
  ShieldCheck,
  TimerReset,
  Wrench,
} from "lucide-react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusPill,
} from "@/components/ui";
import { apiGet, demoMode } from "@/lib/api-client";
import { formatDate, shortId, titleCase } from "@/lib/format";
import type {
  Agent,
  AuditEvent,
  Execution,
  Policy,
  SecurityDetector,
  SecurityFinding,
  Tool,
} from "@/lib/types";

function QueryBoundary<T>({
  data,
  error,
  loading,
  children,
  empty,
}: {
  data: T[] | undefined;
  error: Error | null;
  loading: boolean;
  children: (items: T[]) => React.ReactNode;
  empty: string;
}) {
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!data?.length)
    return <EmptyState title="No records yet" message={empty} />;
  return children(data);
}

export function AgentsView() {
  const query = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<Agent[]>("/agents"),
  });
  return (
    <>
      <PageHeader
        eyebrow="Identity and limits"
        title="Agents"
        description="Review lifecycle state, environments, risk, and reliability budgets for every registered agent."
      />
      <QueryBoundary
        data={query.data}
        error={query.error}
        loading={query.isLoading}
        empty="Register an agent through the API to begin controlling its tool access."
      >
        {(agents) => (
          <div className="agent-grid">
            {agents.map((agent) => (
              <article className="agent-card" key={agent.id}>
                <header>
                  <span className="agent-avatar">
                    <Bot size={22} />
                  </span>
                  <div>
                    <h2>{agent.name}</h2>
                    <p>{agent.description ?? "No description provided"}</p>
                  </div>
                  <StatusPill value={agent.status} />
                </header>
                <div className="agent-meta">
                  <div>
                    <span>Risk tier</span>
                    <StatusPill value={agent.risk_tier} />
                  </div>
                  <div>
                    <span>Environments</span>
                    <strong>{agent.allowed_environments.join(", ")}</strong>
                  </div>
                  <div>
                    <span>Daily budget</span>
                    <strong>
                      {agent.budget_config.max_executions_per_day.toLocaleString()}{" "}
                      executions
                    </strong>
                  </div>
                  <div>
                    <span>Rate limit</span>
                    <strong>
                      {agent.budget_config.max_decisions_per_minute}/minute
                    </strong>
                  </div>
                </div>
                <footer>
                  <span>Updated {formatDate(agent.updated_at)}</span>
                  <span className="mono">{shortId(agent.id)}</span>
                </footer>
              </article>
            ))}
          </div>
        )}
      </QueryBoundary>
    </>
  );
}

export function ToolsView() {
  const query = useQuery({
    queryKey: ["tools"],
    queryFn: () => apiGet<Tool[]>("/tools"),
  });
  return (
    <>
      <PageHeader
        eyebrow="Registered capabilities"
        title="Tools"
        description="Inspect adapter bindings, input contracts, timeouts, and capability classifications."
      />
      <Panel
        title="Tool registry"
        subtitle="Only registered adapters can be selected for controlled execution"
      >
        <QueryBoundary
          data={query.data}
          error={query.error}
          loading={query.isLoading}
          empty="Register the first controlled tool through the API."
        >
          {(tools) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Risk</th>
                    <th>Capabilities</th>
                    <th>Adapter</th>
                    <th>Timeout</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((tool) => (
                    <tr key={tool.id}>
                      <td>
                        <span className="name-cell">
                          <i>
                            <Wrench size={16} />
                          </i>
                          <span>
                            <strong>{tool.name}</strong>
                            <small>
                              {tool.description ?? shortId(tool.id)}
                            </small>
                          </span>
                        </span>
                      </td>
                      <td>
                        <StatusPill value={tool.risk_class} />
                      </td>
                      <td>
                        <div className="tag-list">
                          {tool.capability_flags.map((flag) => (
                            <span key={flag}>{titleCase(flag)}</span>
                          ))}
                        </div>
                      </td>
                      <td>
                        <span className="mono">
                          {tool.adapter_name}@{tool.adapter_version}
                        </span>
                      </td>
                      <td>{tool.execution_timeout_seconds}s</td>
                      <td>
                        <StatusPill value={tool.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBoundary>
      </Panel>
    </>
  );
}

export function PoliciesView() {
  const query = useQuery({
    queryKey: ["policies"],
    queryFn: () => apiGet<Policy[]>("/policies"),
  });
  return (
    <>
      <PageHeader
        eyebrow="Deterministic enforcement"
        title="Policies"
        description="Active immutable policy versions evaluated before any execution authority is granted."
      />
      <Panel
        title="Policy set"
        subtitle="Deny outcomes always take precedence over approval requirements"
      >
        <QueryBoundary
          data={query.data}
          error={query.error}
          loading={query.isLoading}
          empty="Create a deny or approval policy through the API."
        >
          {(policies) => (
            <div className="policy-list">
              {policies.map((policy) => (
                <article key={policy.id}>
                  <div className="policy-priority">{policy.priority}</div>
                  <div className="policy-copy">
                    <div>
                      <h3>{policy.name}</h3>
                      <StatusPill value={policy.status} />
                    </div>
                    <p>{policy.description ?? "No policy description"}</p>
                    <div className="policy-details">
                      <span>
                        <ShieldCheck size={15} />{" "}
                        {titleCase(policy.document.effect)}
                      </span>
                      <span>
                        Reason: <b>{policy.document.reason_code}</b>
                      </span>
                      <span>
                        {policy.document.conditions.length} conditions
                      </span>
                      <span>v{policy.current_version}</span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </QueryBoundary>
      </Panel>
    </>
  );
}

export function RunsView() {
  const query = useQuery({
    queryKey: ["executions"],
    queryFn: () => apiGet<Execution[]>("/executions"),
  });
  return (
    <>
      <PageHeader
        eyebrow="Durable execution trace"
        title="Agent runs"
        description="Track authorization, attempts, adapter outcomes, timeouts, and safe retry state."
      />
      <Panel
        title="Execution history"
        subtitle="Every row is bound to one durable policy decision"
      >
        <QueryBoundary
          data={query.data}
          error={query.error}
          loading={query.isLoading}
          empty="Agent executions will appear after an allowed or approved decision."
        >
          {(runs) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Execution</th>
                    <th>Operation</th>
                    <th>Environment</th>
                    <th>Adapter</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Started</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id}>
                      <td className="mono">{shortId(run.id)}</td>
                      <td>
                        <strong>{titleCase(run.operation)}</strong>
                      </td>
                      <td>{titleCase(run.environment)}</td>
                      <td className="mono">
                        {run.adapter_name}@{run.adapter_version}
                      </td>
                      <td>
                        <StatusPill value={run.status} />
                      </td>
                      <td>
                        {run.attempt_count}/{run.max_attempts}
                      </td>
                      <td>{formatDate(run.started_at)}</td>
                      <td>
                        {run.error_code ? (
                          <span className="error-code">{run.error_code}</span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBoundary>
      </Panel>
    </>
  );
}

export function SecurityView() {
  const findings = useQuery({
    queryKey: ["findings"],
    queryFn: () => apiGet<SecurityFinding[]>("/security/findings"),
  });
  const detectors = useQuery({
    queryKey: ["detectors"],
    queryFn: () => apiGet<SecurityDetector[]>("/security/detectors"),
  });
  return (
    <>
      <PageHeader
        eyebrow="Pre-execution inspection"
        title="Security events"
        description="Review sanitized evidence from secret, PII, and prompt-manipulation detectors."
      />
      <div className="security-summary">
        <span>
          <ShieldCheck size={20} />
          <b>
            {detectors.data?.filter((item) => item.status === "active")
              .length ?? 0}
          </b>{" "}
          active detectors
        </span>
        <span>
          <Gauge size={20} />
          <b>{findings.data?.length ?? 0}</b> recent findings
        </span>
        <span>
          <TimerReset size={20} />
          <b>100k</b> character scan bound
        </span>
      </div>
      <div className="two-column">
        <Panel
          title="Detector registry"
          subtitle="Versioned deterministic controls"
        >
          <QueryBoundary
            data={detectors.data}
            error={detectors.error}
            loading={detectors.isLoading}
            empty="Configure a security detector through the API."
          >
            {(items) => (
              <div className="compact-list">
                {items.map((item) => (
                  <div key={item.id}>
                    <span className="detector-icon">
                      <ShieldCheck size={17} />
                    </span>
                    <span>
                      <strong>{item.name}</strong>
                      <small>
                        {titleCase(item.document.kind)} ·{" "}
                        {item.document.reason_code}
                      </small>
                    </span>
                    <StatusPill value={item.status} />
                  </div>
                ))}
              </div>
            )}
          </QueryBoundary>
        </Panel>
        <Panel
          title="Latest findings"
          subtitle="Matched values are never returned"
        >
          <QueryBoundary
            data={findings.data}
            error={findings.error}
            loading={findings.isLoading}
            empty="No detector findings have been recorded."
          >
            {(items) => (
              <div className="compact-list">
                {items.map((item) => (
                  <div key={item.id}>
                    <span>
                      <strong>{titleCase(item.category)}</strong>
                      <small>
                        {item.location} · {formatDate(item.created_at)}
                      </small>
                    </span>
                    <StatusPill value={item.severity} />
                  </div>
                ))}
              </div>
            )}
          </QueryBoundary>
        </Panel>
      </div>
    </>
  );
}

export function AuditView() {
  const query = useQuery({
    queryKey: ["audit"],
    queryFn: () => apiGet<AuditEvent[]>("/audit"),
  });
  return (
    <>
      <PageHeader
        eyebrow="Accountability"
        title="Audit log"
        description="Inspect tenant-scoped, sanitized security and administration events."
      />
      <Panel
        title="Recorded events"
        subtitle="Snapshots are represented by hashes, never raw sensitive payloads"
      >
        <QueryBoundary
          data={query.data}
          error={query.error}
          loading={query.isLoading}
          empty="Audit events appear as users and agents change protected resources."
        >
          {(events) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Target ID</th>
                    <th>Request ID</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id}>
                      <td>{formatDate(event.created_at)}</td>
                      <td>
                        <StatusPill value={event.actor_type} />
                      </td>
                      <td>
                        <strong>{event.action}</strong>
                      </td>
                      <td>{titleCase(event.target_type)}</td>
                      <td className="mono">{shortId(event.target_id)}</td>
                      <td className="mono">{event.request_id ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBoundary>
      </Panel>
    </>
  );
}

export function SettingsView() {
  const checks = [
    {
      icon: Server,
      label: "FastAPI gateway",
      value: demoMode ? "Demo connection" : "Same-origin proxy",
      tone: "Protected",
    },
    {
      icon: Database,
      label: "PostgreSQL",
      value: "Authoritative state",
      tone: "Required",
    },
    {
      icon: Network,
      label: "Redis + Celery",
      value: "Maintenance queue",
      tone: "Phase 6",
    },
    {
      icon: CheckCircle2,
      label: "Security model",
      value: "Deterministic deny",
      tone: "Enforced",
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Workspace configuration"
        title="Settings"
        description="Review frontend connectivity and the active control-plane architecture."
      />
      <div className="settings-grid">
        {checks.map((check) => (
          <article key={check.label}>
            <span>
              <check.icon size={21} />
            </span>
            <div>
              <p>{check.label}</p>
              <strong>{check.value}</strong>
            </div>
            <em>{check.tone}</em>
          </article>
        ))}
      </div>
      <Panel
        title="Local startup"
        subtitle="Run these services from separate PowerShell terminals"
      >
        <div className="command-list">
          <div>
            <span>1</span>
            <code>docker compose up -d postgres redis</code>
          </div>
          <div>
            <span>2</span>
            <code>uv run uvicorn backend.app.main:app --reload</code>
          </div>
          <div>
            <span>3</span>
            <code>pnpm --dir frontend dev</code>
          </div>
          <div>
            <span>4</span>
            <code>
              uv run celery -A backend.app.worker:celery_app worker --pool=solo
            </code>
          </div>
        </div>
      </Panel>
    </>
  );
}
