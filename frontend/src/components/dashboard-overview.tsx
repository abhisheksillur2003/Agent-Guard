"use client";

import { useQueries } from "@tanstack/react-query";
import { Activity, Bot, CircleAlert, Clock3, ShieldCheck } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ErrorState,
  MetricCard,
  PageHeader,
  Panel,
  StatusPill,
} from "@/components/ui";
import { apiGet } from "@/lib/api-client";
import { formatDate, titleCase } from "@/lib/format";
import type { Agent, Approval, Execution, SecurityFinding } from "@/lib/types";

const riskColors = ["#14b8a6", "#f59e0b", "#f97316", "#ef4444"];

export function DashboardOverview() {
  const results = useQueries({
    queries: [
      { queryKey: ["agents"], queryFn: () => apiGet<Agent[]>("/agents") },
      {
        queryKey: ["executions"],
        queryFn: () => apiGet<Execution[]>("/executions"),
      },
      {
        queryKey: ["approvals"],
        queryFn: () => apiGet<Approval[]>("/approvals"),
      },
      {
        queryKey: ["findings"],
        queryFn: () => apiGet<SecurityFinding[]>("/security/findings"),
      },
    ],
  });
  const firstError = results.find((result) => result.error)?.error;
  if (firstError) return <ErrorState error={firstError} />;

  const agents = results[0].data ?? [];
  const executions = results[1].data ?? [];
  const approvals = results[2].data ?? [];
  const findings = results[3].data ?? [];
  const pending = approvals.filter((item) => item.status === "pending").length;
  const blocked =
    findings.filter((item) => item.action === "deny").length +
    executions.filter((item) => item.status === "failed").length;
  const successful = executions.filter(
    (item) => item.status === "succeeded",
  ).length;

  const activityData = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    const daily = executions.filter(
      (item) => item.created_at.slice(0, 10) === key,
    );
    return {
      day: date.toLocaleDateString("en", { weekday: "short" }),
      successful: daily.filter((item) => item.status === "succeeded").length,
      blocked: daily.filter((item) =>
        ["failed", "timed_out"].includes(item.status),
      ).length,
      review: approvals.filter((item) => item.created_at.slice(0, 10) === key)
        .length,
    };
  });
  const riskData = ["low", "medium", "high", "critical"].map((risk) => ({
    name: titleCase(risk),
    value: agents.filter((agent) => agent.risk_tier === risk).length,
  }));
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.name]));

  return (
    <>
      <PageHeader
        eyebrow="Operations overview"
        title="Dashboard"
        description="Monitor agent activity, risk, approvals, and execution health from one control plane."
        action={
          <span className="range-chip">
            <Clock3 size={15} /> Last 7 days
          </span>
        }
      />
      <div className="metrics-grid">
        <MetricCard
          label="Active agents"
          value={agents.filter((item) => item.status === "active").length}
          hint={`${agents.length} registered`}
          icon={Bot}
        />
        <MetricCard
          label="Total runs"
          value={executions.length}
          hint={`${successful} successful`}
          icon={Activity}
          tone="green"
        />
        <MetricCard
          label="Blocked"
          value={blocked}
          hint="Policy or runtime"
          icon={ShieldCheck}
          tone="red"
        />
        <MetricCard
          label="Awaiting approval"
          value={pending}
          hint="Human decision needed"
          icon={CircleAlert}
          tone="amber"
        />
      </div>
      <div className="dashboard-grid">
        <Panel
          title="Agent activity"
          subtitle="Execution outcomes across the last seven days"
          className="activity-panel"
        >
          <div className="chart-legend">
            <span className="legend-success">Successful</span>
            <span className="legend-danger">Blocked</span>
            <span className="legend-warning">Needs review</span>
          </div>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={activityData}
                margin={{ top: 10, right: 12, left: -18, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="successFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.28} />
                    <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#e5edf5"
                />
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#718096", fontSize: 12 }}
                />
                <YAxis
                  allowDecimals={false}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#718096", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #dbe7f1",
                    boxShadow: "0 12px 30px rgba(15,23,42,.12)",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="successful"
                  stroke="#0ea5e9"
                  strokeWidth={2.5}
                  fill="url(#successFill)"
                />
                <Area
                  type="monotone"
                  dataKey="blocked"
                  stroke="#ef4444"
                  strokeWidth={2}
                  fill="transparent"
                />
                <Area
                  type="monotone"
                  dataKey="review"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  fill="transparent"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel
          title="Risk distribution"
          subtitle="Registered agents by risk tier"
          className="risk-panel"
        >
          <div className="risk-chart">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={riskData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={82}
                  paddingAngle={3}
                >
                  {riskData.map((entry, index) => (
                    <Cell key={entry.name} fill={riskColors[index]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="risk-total">
              <strong>{agents.length}</strong>
              <span>Agents</span>
            </div>
          </div>
          <div className="risk-list">
            {riskData.map((item, index) => (
              <div key={item.name}>
                <span>
                  <i style={{ background: riskColors[index] }} />
                  {item.name}
                </span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </Panel>
        <Panel
          title="Recent agent runs"
          subtitle="Latest durable execution records"
          className="recent-runs"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Operation</th>
                  <th>Environment</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {executions.slice(0, 7).map((run) => (
                  <tr key={run.id}>
                    <td>
                      <strong>
                        {agentNames.get(run.agent_id) ?? "Unknown agent"}
                      </strong>
                    </td>
                    <td>{titleCase(run.operation)}</td>
                    <td>{titleCase(run.environment)}</td>
                    <td>
                      <StatusPill value={run.status} />
                    </td>
                    <td>
                      {run.attempt_count}/{run.max_attempts}
                    </td>
                    <td>{formatDate(run.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  );
}
