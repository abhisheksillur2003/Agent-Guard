"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Check,
  Clipboard,
  KeyRound,
  Pencil,
  Plus,
  Power,
  ShieldCheck,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useState } from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusPill,
} from "@/components/ui";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  demoMode,
  getCurrentUser,
} from "@/lib/api-client";
import { formatDate, shortId, titleCase } from "@/lib/format";
import type {
  Agent,
  AgentCredential,
  AgentPermission,
  CurrentUser,
  ReliabilityBudget,
  RiskTier,
  Tool,
} from "@/lib/types";

const riskTiers: RiskTier[] = ["low", "medium", "high", "critical"];
const capabilities = [
  "read_only",
  "write",
  "destructive",
  "financial",
  "external_egress",
  "code_execution",
] as const;

function splitList(value: string): string[] {
  return [
    ...new Set(
      value
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
    ),
  ];
}

function Modal({
  title,
  description,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  description: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className={`management-modal${wide ? " management-modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

function FormError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="form-error" role="alert">
      {error instanceof Error
        ? error.message
        : "The request could not be completed"}
    </div>
  );
}

function ManagementNotice({ user }: { user?: CurrentUser }) {
  if (demoMode)
    return (
      <p className="management-notice">
        Demo records are read-only. Sign in to manage live data.
      </p>
    );
  if (user && !["admin", "developer"].includes(user.role))
    return (
      <p className="management-notice">
        Your role has read-only access to this registry.
      </p>
    );
  return null;
}

type AgentFormState = {
  name: string;
  description: string;
  riskTier: RiskTier;
  environments: string;
  maxDecisions: number;
  maxExecutions: number;
  maxIdentical: number;
  loopWindow: number;
  maxAttempts: number;
  retryBackoff: number;
};

function agentFormState(agent?: Agent): AgentFormState {
  return {
    name: agent?.name ?? "",
    description: agent?.description ?? "",
    riskTier: agent?.risk_tier ?? "medium",
    environments: agent?.allowed_environments.join(", ") ?? "local",
    maxDecisions: agent?.budget_config.max_decisions_per_minute ?? 60,
    maxExecutions: agent?.budget_config.max_executions_per_day ?? 1000,
    maxIdentical: agent?.budget_config.max_identical_requests_in_window ?? 5,
    loopWindow: agent?.budget_config.loop_detection_window_seconds ?? 60,
    maxAttempts: agent?.budget_config.max_execution_attempts ?? 2,
    retryBackoff: agent?.budget_config.retry_backoff_seconds ?? 5,
  };
}

function AgentForm({ agent, onClose }: { agent?: Agent; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => agentFormState(agent));
  const mutation = useMutation({
    mutationFn: () => {
      const budget_config: ReliabilityBudget = {
        max_decisions_per_minute: form.maxDecisions,
        max_executions_per_day: form.maxExecutions,
        max_identical_requests_in_window: form.maxIdentical,
        loop_detection_window_seconds: form.loopWindow,
        max_execution_attempts: form.maxAttempts,
        retry_backoff_seconds: form.retryBackoff,
      };
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        risk_tier: form.riskTier,
        allowed_environments: splitList(form.environments),
        budget_config,
      };
      return agent
        ? apiPatch<Agent>(`/agents/${agent.id}`, payload)
        : apiPost<Agent>("/agents", payload);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents"] }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]);
      onClose();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal
      title={agent ? "Edit agent" : "Register agent"}
      description="Define identity, permitted environments, risk, and bounded reliability limits."
      onClose={onClose}
      wide
    >
      <form className="management-form" onSubmit={submit}>
        <div className="form-grid">
          <label>
            <span>Name</span>
            <input
              required
              minLength={2}
              maxLength={120}
              value={form.name}
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
              placeholder="Customer Support Agent"
            />
          </label>
          <label>
            <span>Risk tier</span>
            <select
              value={form.riskTier}
              onChange={(event) =>
                setForm({ ...form, riskTier: event.target.value as RiskTier })
              }
            >
              {riskTiers.map((tier) => (
                <option key={tier} value={tier}>
                  {titleCase(tier)}
                </option>
              ))}
            </select>
          </label>
          <label className="form-span">
            <span>Description</span>
            <textarea
              maxLength={2000}
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
              placeholder="Describe the agent's approved purpose."
            />
          </label>
          <label className="form-span">
            <span>Allowed environments</span>
            <input
              required
              value={form.environments}
              onChange={(event) =>
                setForm({ ...form, environments: event.target.value })
              }
              placeholder="local, staging, production"
            />
            <small>
              Comma-separated. Requests outside this list are denied.
            </small>
          </label>
        </div>
        <fieldset>
          <legend>Reliability budget</legend>
          <div className="form-grid form-grid-three">
            <NumberField
              label="Decisions / minute"
              value={form.maxDecisions}
              min={1}
              onChange={(value) => setForm({ ...form, maxDecisions: value })}
            />
            <NumberField
              label="Executions / day"
              value={form.maxExecutions}
              min={1}
              onChange={(value) => setForm({ ...form, maxExecutions: value })}
            />
            <NumberField
              label="Identical requests"
              value={form.maxIdentical}
              min={2}
              onChange={(value) => setForm({ ...form, maxIdentical: value })}
            />
            <NumberField
              label="Loop window (seconds)"
              value={form.loopWindow}
              min={10}
              onChange={(value) => setForm({ ...form, loopWindow: value })}
            />
            <NumberField
              label="Execution attempts"
              value={form.maxAttempts}
              min={1}
              max={5}
              onChange={(value) => setForm({ ...form, maxAttempts: value })}
            />
            <NumberField
              label="Retry backoff (seconds)"
              value={form.retryBackoff}
              min={1}
              onChange={(value) => setForm({ ...form, retryBackoff: value })}
            />
          </div>
        </fieldset>
        <FormError error={mutation.error} />
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary-button"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending
              ? "Saving…"
              : agent
                ? "Save agent"
                : "Register agent"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        type="number"
        required
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function CredentialDialog({
  agent,
  mode,
  onClose,
}: {
  agent: Agent;
  mode: "issue" | "rotate";
  onClose: () => void;
}) {
  const [expiresAt, setExpiresAt] = useState("");
  const [result, setResult] = useState<AgentCredential>();
  const [copied, setCopied] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      apiPost<AgentCredential>(
        `/agents/${agent.id}/credentials${mode === "rotate" ? "/rotate" : ""}`,
        { expires_at: expiresAt ? new Date(expiresAt).toISOString() : null },
      ),
    onSuccess: setResult,
  });

  async function copyCredential() {
    if (!result) return;
    await navigator.clipboard.writeText(result.credential);
    setCopied(true);
  }

  return (
    <Modal
      title={
        result
          ? "Store credential now"
          : mode === "rotate"
            ? "Rotate credential"
            : "Issue credential"
      }
      description={
        result
          ? result.warning
          : `${titleCase(mode)} an authentication key for ${agent.name}.`
      }
      onClose={onClose}
    >
      {result ? (
        <div className="credential-result">
          <p>
            The secret is shown once. AgentGuard stores only its keyed hash.
          </p>
          <code>{result.credential}</code>
          <button
            className="primary-button"
            type="button"
            onClick={copyCredential}
          >
            {copied ? <Check size={16} /> : <Clipboard size={16} />}
            {copied ? "Copied" : "Copy credential"}
          </button>
          <small>
            Key prefix: {result.key_prefix} · Expires:{" "}
            {result.expires_at ? formatDate(result.expires_at) : "Never"}
          </small>
        </div>
      ) : (
        <form
          className="management-form"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          {mode === "rotate" && (
            <p className="destructive-note">
              Rotation immediately revokes every active credential for this
              agent.
            </p>
          )}
          <label>
            <span>Expiry (optional)</span>
            <input
              type="datetime-local"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </label>
          <FormError error={mutation.error} />
          <div className="form-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={mutation.isPending}
            >
              {mutation.isPending
                ? "Generating…"
                : mode === "rotate"
                  ? "Rotate credential"
                  : "Issue credential"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function PermissionsDialog({
  agent,
  tools,
  onClose,
}: {
  agent: Agent;
  tools: Tool[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [toolId, setToolId] = useState(tools[0]?.id ?? "");
  const [operations, setOperations] = useState("read");
  const [constraints, setConstraints] = useState("{}");
  const [localError, setLocalError] = useState("");
  const queryKey = ["permissions", agent.id];
  const permissions = useQuery({
    queryKey,
    queryFn: () => apiGet<AgentPermission[]>(`/agents/${agent.id}/permissions`),
  });
  const grant = useMutation({
    mutationFn: () => {
      setLocalError("");
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(constraints) as Record<string, unknown>;
      } catch {
        throw new Error("Constraints must be valid JSON");
      }
      return apiPut<AgentPermission>(
        `/agents/${agent.id}/permissions/${toolId}`,
        {
          operations: splitList(operations),
          constraints: parsed,
        },
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]);
    },
  });
  const remove = useMutation({
    mutationFn: (permission: AgentPermission) =>
      apiDelete<{ message: string }>(
        `/agents/${agent.id}/permissions/${permission.tool_id}`,
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]);
    },
  });
  const toolMap = new Map(tools.map((tool) => [tool.id, tool.name]));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!toolId) {
      setLocalError("Register a tool before granting permissions");
      return;
    }
    if (!splitList(operations).length) {
      setLocalError("Enter at least one operation");
      return;
    }
    grant.mutate();
  }

  return (
    <Modal
      title="Tool permissions"
      description={`Grant explicit operations to ${agent.name}.`}
      onClose={onClose}
      wide
    >
      <div className="permission-layout">
        <form className="management-form" onSubmit={submit}>
          <label>
            <span>Tool</span>
            <select
              value={toolId}
              onChange={(event) => setToolId(event.target.value)}
              disabled={!tools.length}
            >
              {!tools.length && <option value="">No tools registered</option>}
              {tools.map((tool) => (
                <option key={tool.id} value={tool.id}>
                  {tool.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Allowed operations</span>
            <input
              value={operations}
              onChange={(event) => setOperations(event.target.value)}
              placeholder="read, search, refund"
            />
            <small>Comma-separated operation names.</small>
          </label>
          <label>
            <span>Constraints JSON</span>
            <textarea
              className="code-input"
              value={constraints}
              onChange={(event) => setConstraints(event.target.value)}
            />
          </label>
          {(localError || grant.error) && (
            <FormError
              error={localError ? new Error(localError) : grant.error}
            />
          )}
          <button
            className="primary-button"
            type="submit"
            disabled={grant.isPending || !tools.length}
          >
            {grant.isPending ? "Saving…" : "Grant or update permission"}
          </button>
        </form>
        <div className="permission-list">
          <h3>Current grants</h3>
          {permissions.isLoading && (
            <LoadingState label="Loading permissions" />
          )}
          {permissions.error && <ErrorState error={permissions.error} />}
          {!permissions.isLoading && !permissions.data?.length && (
            <EmptyState
              title="No permissions"
              message="This agent is denied access to every tool."
            />
          )}
          {permissions.data?.map((permission) => (
            <article key={permission.id}>
              <div>
                <strong>
                  {toolMap.get(permission.tool_id) ??
                    shortId(permission.tool_id)}
                </strong>
                <span>{permission.operations.join(", ")}</span>
              </div>
              <button
                className="icon-button danger-icon"
                type="button"
                onClick={() => remove.mutate(permission)}
                disabled={remove.isPending}
                aria-label="Remove permission"
              >
                <Trash2 size={16} />
              </button>
            </article>
          ))}
          <FormError error={remove.error} />
        </div>
      </div>
    </Modal>
  );
}

export function AgentsView() {
  const queryClient = useQueryClient();
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<Agent[]>("/agents"),
  });
  const tools = useQuery({
    queryKey: ["tools"],
    queryFn: () => apiGet<Tool[]>("/tools"),
  });
  const session = useQuery({ queryKey: ["session"], queryFn: getCurrentUser });
  const [editing, setEditing] = useState<Agent | "new">();
  const [credential, setCredential] = useState<{
    agent: Agent;
    mode: "issue" | "rotate";
  }>();
  const [permissionAgent, setPermissionAgent] = useState<Agent>();
  const canEdit =
    !demoMode && ["admin", "developer"].includes(session.data?.role ?? "");
  const isAdmin = !demoMode && session.data?.role === "admin";
  const lifecycle = useMutation({
    mutationFn: ({
      agent,
      action,
    }: {
      agent: Agent;
      action: "activate" | "suspend";
    }) => apiPost<Agent>(`/agents/${agent.id}/${action}`, {}),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents"] }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]);
    },
  });

  return (
    <>
      <PageHeader
        eyebrow="Identity and limits"
        title="Agents"
        description="Register agents, control lifecycle and credentials, and grant explicit tool operations."
        action={
          canEdit && (
            <button
              className="primary-button"
              onClick={() => setEditing("new")}
            >
              <Plus size={16} /> Register agent
            </button>
          )
        }
      />
      <ManagementNotice user={session.data} />
      {agents.isLoading && <LoadingState />}
      {agents.error && <ErrorState error={agents.error} />}
      {!agents.isLoading && !agents.data?.length && (
        <EmptyState
          title="No agents registered"
          message="Register an agent to begin controlling its tool access."
        />
      )}
      {!!agents.data?.length && (
        <div className="agent-grid">
          {agents.data.map((agent) => (
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
              {canEdit && (
                <div className="card-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setEditing(agent)}
                  >
                    <Pencil size={15} /> Edit
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => setCredential({ agent, mode: "issue" })}
                  >
                    <KeyRound size={15} /> Issue key
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => setCredential({ agent, mode: "rotate" })}
                  >
                    <KeyRound size={15} /> Rotate key
                  </button>
                  {isAdmin && (
                    <button
                      className="secondary-button"
                      onClick={() => setPermissionAgent(agent)}
                    >
                      <ShieldCheck size={15} /> Permissions
                    </button>
                  )}
                  {isAdmin && agent.status !== "revoked" && (
                    <button
                      className="secondary-button"
                      onClick={() =>
                        lifecycle.mutate({
                          agent,
                          action:
                            agent.status === "active" ? "suspend" : "activate",
                        })
                      }
                      disabled={lifecycle.isPending}
                    >
                      <Power size={15} />{" "}
                      {agent.status === "active" ? "Suspend" : "Activate"}
                    </button>
                  )}
                </div>
              )}
              <footer>
                <span>Updated {formatDate(agent.updated_at)}</span>
                <span className="mono">{shortId(agent.id)}</span>
              </footer>
            </article>
          ))}
        </div>
      )}
      <FormError error={lifecycle.error} />
      {editing && (
        <AgentForm
          agent={editing === "new" ? undefined : editing}
          onClose={() => setEditing(undefined)}
        />
      )}
      {credential && (
        <CredentialDialog
          {...credential}
          onClose={() => setCredential(undefined)}
        />
      )}
      {permissionAgent && (
        <PermissionsDialog
          agent={permissionAgent}
          tools={tools.data ?? []}
          onClose={() => setPermissionAgent(undefined)}
        />
      )}
    </>
  );
}

type ToolFormState = {
  name: string;
  description: string;
  riskClass: RiskTier;
  selectedCapabilities: string[];
  schema: string;
  timeout: number;
  status: "active" | "disabled";
};

function toolFormState(tool?: Tool): ToolFormState {
  return {
    name: tool?.name ?? "",
    description: tool?.description ?? "",
    riskClass: tool?.risk_class ?? "low",
    selectedCapabilities: tool?.capability_flags ?? ["read_only"],
    schema: JSON.stringify(
      tool?.input_schema ?? { type: "object", additionalProperties: false },
      null,
      2,
    ),
    timeout: tool?.execution_timeout_seconds ?? 10,
    status: tool?.status ?? "active",
  };
}

function ToolForm({
  tool,
  user,
  onClose,
}: {
  tool?: Tool;
  user: CurrentUser;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => toolFormState(tool));
  const [localError, setLocalError] = useState("");
  const mutation = useMutation({
    mutationFn: () => {
      setLocalError("");
      let input_schema: Record<string, unknown>;
      try {
        input_schema = JSON.parse(form.schema) as Record<string, unknown>;
      } catch {
        throw new Error("Input schema must be valid JSON");
      }
      const common = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        input_schema,
      };
      const protectedFields = {
        risk_class: form.riskClass,
        capability_flags: form.selectedCapabilities,
        adapter_name: "safe_echo",
        adapter_version: "1",
        execution_timeout_seconds: form.timeout,
      };
      if (!tool)
        return apiPost<Tool>("/tools", { ...common, ...protectedFields });
      return apiPatch<Tool>(
        `/tools/${tool.id}`,
        user.role === "admin"
          ? { ...common, ...protectedFields, status: form.status }
          : common,
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tools"] }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]);
      onClose();
    },
  });

  function toggleCapability(capability: string) {
    setForm({
      ...form,
      selectedCapabilities: form.selectedCapabilities.includes(capability)
        ? form.selectedCapabilities.filter((item) => item !== capability)
        : [...form.selectedCapabilities, capability],
    });
  }

  return (
    <Modal
      title={tool ? "Edit tool" : "Register tool"}
      description="Bind a validated JSON contract to an approved adapter."
      onClose={onClose}
      wide
    >
      <form
        className="management-form"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="form-grid">
          <label>
            <span>Name</span>
            <input
              required
              minLength={2}
              maxLength={120}
              value={form.name}
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
              placeholder="Search orders"
            />
          </label>
          <label>
            <span>Risk class</span>
            <select
              value={form.riskClass}
              disabled={!!tool && user.role !== "admin"}
              onChange={(event) =>
                setForm({ ...form, riskClass: event.target.value as RiskTier })
              }
            >
              {riskTiers.map((tier) => (
                <option key={tier} value={tier}>
                  {titleCase(tier)}
                </option>
              ))}
            </select>
          </label>
          <label className="form-span">
            <span>Description</span>
            <textarea
              maxLength={2000}
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
            />
          </label>
          <label>
            <span>Adapter</span>
            <input value="safe_echo@1" disabled />
          </label>
          <NumberField
            label="Timeout (seconds)"
            value={form.timeout}
            min={1}
            max={60}
            onChange={(value) => setForm({ ...form, timeout: value })}
          />
          {tool && user.role === "admin" && (
            <label>
              <span>Status</span>
              <select
                value={form.status}
                onChange={(event) =>
                  setForm({
                    ...form,
                    status: event.target.value as ToolFormState["status"],
                  })
                }
              >
                <option value="active">Active</option>
                <option value="disabled">Disabled</option>
              </select>
            </label>
          )}
        </div>
        <fieldset disabled={!!tool && user.role !== "admin"}>
          <legend>Capability flags</legend>
          <div className="checkbox-grid">
            {capabilities.map((capability) => (
              <label key={capability}>
                <input
                  type="checkbox"
                  checked={form.selectedCapabilities.includes(capability)}
                  onChange={() => toggleCapability(capability)}
                />
                <span>{titleCase(capability)}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label>
          <span>Input JSON Schema</span>
          <textarea
            className="code-input schema-input"
            value={form.schema}
            onChange={(event) =>
              setForm({ ...form, schema: event.target.value })
            }
          />
        </label>
        {(localError || mutation.error) && (
          <FormError
            error={localError ? new Error(localError) : mutation.error}
          />
        )}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary-button"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending
              ? "Saving…"
              : tool
                ? "Save tool"
                : "Register tool"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function ToolsView() {
  const tools = useQuery({
    queryKey: ["tools"],
    queryFn: () => apiGet<Tool[]>("/tools"),
  });
  const session = useQuery({ queryKey: ["session"], queryFn: getCurrentUser });
  const [editing, setEditing] = useState<Tool | "new">();
  const canEdit =
    !demoMode && ["admin", "developer"].includes(session.data?.role ?? "");

  return (
    <>
      <PageHeader
        eyebrow="Registered capabilities"
        title="Tools"
        description="Register validated tool contracts and manage adapter, risk, timeout, and lifecycle settings."
        action={
          canEdit && (
            <button
              className="primary-button"
              onClick={() => setEditing("new")}
            >
              <Plus size={16} /> Register tool
            </button>
          )
        }
      />
      <ManagementNotice user={session.data} />
      <Panel
        title="Tool registry"
        subtitle="Only registered adapters can be selected for controlled execution"
      >
        {tools.isLoading && <LoadingState />}
        {tools.error && <ErrorState error={tools.error} />}
        {!tools.isLoading && !tools.data?.length && (
          <EmptyState
            title="No tools registered"
            message="Register the first controlled tool to grant agent access."
          />
        )}
        {!!tools.data?.length && (
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
                  {canEdit && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {tools.data.map((tool) => (
                  <tr key={tool.id}>
                    <td>
                      <span className="name-cell">
                        <i>
                          <Wrench size={16} />
                        </i>
                        <span>
                          <strong>{tool.name}</strong>
                          <small>{tool.description ?? shortId(tool.id)}</small>
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
                    {canEdit && (
                      <td>
                        <button
                          className="secondary-button compact-button"
                          onClick={() => setEditing(tool)}
                        >
                          <Pencil size={14} /> Edit
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {editing && session.data && (
        <ToolForm
          tool={editing === "new" ? undefined : editing}
          user={session.data}
          onClose={() => setEditing(undefined)}
        />
      )}
    </>
  );
}
