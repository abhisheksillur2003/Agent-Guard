import type {
  Agent,
  Approval,
  AuditEvent,
  CurrentUser,
  Execution,
  Policy,
  SecurityDetector,
  SecurityFinding,
  Tool,
} from "@/lib/types";

const org = "10000000-0000-4000-8000-000000000001";
const iso = (day: number, hour = 10) =>
  `2026-09-${String(day).padStart(2, "0")}T${String(hour).padStart(2, "0")}:00:00Z`;
const budget = {
  max_decisions_per_minute: 60,
  max_executions_per_day: 1000,
  max_identical_requests_in_window: 5,
  loop_detection_window_seconds: 60,
  max_execution_attempts: 2,
  retry_backoff_seconds: 5,
};

export const demoUser: CurrentUser = {
  id: "20000000-0000-4000-8000-000000000001",
  organization_id: org,
  email: "admin@agentguard.local",
  role: "admin",
  status: "active",
  created_at: iso(1),
  last_login_at: iso(22, 18),
};

export const demoAgents: Agent[] = [
  [
    "Customer Support Agent",
    "Handles orders, refunds and customer questions.",
    "medium",
    "active",
  ],
  [
    "Invoice Reconciliation",
    "Matches invoices to payments and flags differences.",
    "high",
    "active",
  ],
  [
    "Research Assistant",
    "Collects and summarizes approved public sources.",
    "low",
    "active",
  ],
  [
    "Release Automation",
    "Coordinates deployment checks and release notes.",
    "critical",
    "suspended",
  ],
].map(([name, description, risk, status], index) => ({
  id: `30000000-0000-4000-8000-00000000000${index + 1}`,
  organization_id: org,
  name,
  description,
  owner_user_id: demoUser.id,
  status: status as Agent["status"],
  risk_tier: risk as Agent["risk_tier"],
  allowed_environments:
    index === 2 ? ["local", "staging"] : ["local", "staging", "production"],
  budget_config: budget,
  created_at: iso(8 + index),
  updated_at: iso(22, 12 + index),
}));

export const demoTools: Tool[] = [
  ["Refund order", "financial", "high"],
  ["Search orders", "read_only", "low"],
  ["Send customer email", "external_egress", "medium"],
  ["Update deployment", "code_execution", "critical"],
  ["Safe echo", "read_only", "low"],
].map(([name, capability, risk], index) => ({
  id: `40000000-0000-4000-8000-00000000000${index + 1}`,
  organization_id: org,
  name,
  description: `${name} tool registered with deterministic input validation.`,
  input_schema: { type: "object", additionalProperties: false },
  risk_class: risk as Tool["risk_class"],
  capability_flags: [capability],
  status: "active",
  adapter_name: "safe_echo",
  adapter_version: "1",
  execution_timeout_seconds: 10,
  created_at: iso(10 + index),
  updated_at: iso(22),
}));

export const demoPolicies: Policy[] = [
  [
    "Large refunds require approval",
    "require_approval",
    "REFUND_APPROVAL_REQUIRED",
    10,
  ],
  ["Block production code execution", "deny", "PRODUCTION_CODE_BLOCKED", 20],
  [
    "Review external communications",
    "require_approval",
    "EGRESS_REVIEW_REQUIRED",
    30,
  ],
].map(([name, effect, reason, priority], index) => ({
  id: `50000000-0000-4000-8000-00000000000${index + 1}`,
  organization_id: org,
  name: String(name),
  description:
    "Versioned policy evaluated before execution authority is granted.",
  status: "active",
  priority: Number(priority),
  current_version: index + 1,
  document: {
    scope: {
      agent_ids: [],
      tool_ids: [],
      environments: ["production"],
      operations: [],
    },
    effect: effect as Policy["document"]["effect"],
    reason_code: String(reason),
    conditions: [],
  },
  created_by: demoUser.id,
  created_at: iso(11 + index),
  updated_at: iso(20 + index),
}));

export const demoApprovals: Approval[] = [
  {
    id: "60000000-0000-4000-8000-000000000001",
    organization_id: org,
    decision_id: "61000000-0000-4000-8000-000000000001",
    agent_id: demoAgents[0].id,
    requested_tool_id: demoTools[0].id,
    status: "pending",
    expires_at: iso(23),
    decided_at: null,
    decided_by: null,
    decision_reason: null,
    created_at: iso(22, 16),
    updated_at: iso(22, 16),
  },
  {
    id: "60000000-0000-4000-8000-000000000002",
    organization_id: org,
    decision_id: "61000000-0000-4000-8000-000000000002",
    agent_id: demoAgents[1].id,
    requested_tool_id: demoTools[2].id,
    status: "pending",
    expires_at: iso(23, 4),
    decided_at: null,
    decided_by: null,
    decision_reason: null,
    created_at: iso(22, 15),
    updated_at: iso(22, 15),
  },
];

const runStatuses: Execution["status"][] = [
  "succeeded",
  "succeeded",
  "failed",
  "succeeded",
  "timed_out",
  "succeeded",
  "succeeded",
  "failed",
  "succeeded",
  "running",
];
export const demoExecutions: Execution[] = runStatuses.map((status, index) => ({
  id: `70000000-0000-4000-8000-0000000000${String(index + 1).padStart(2, "0")}`,
  organization_id: org,
  decision_id: `71000000-0000-4000-8000-0000000000${String(index + 1).padStart(2, "0")}`,
  approval_id: null,
  agent_id: demoAgents[index % demoAgents.length].id,
  tool_id: demoTools[index % demoTools.length].id,
  operation: ["search", "refund", "send", "deploy"][index % 4],
  environment: index % 3 === 0 ? "production" : "staging",
  status,
  adapter_name: "safe_echo",
  adapter_version: "1",
  result_summary: status === "succeeded" ? { accepted: true } : {},
  error_code:
    status === "failed"
      ? "ADAPTER_EXECUTION_FAILED"
      : status === "timed_out"
        ? "EXECUTION_TIMEOUT"
        : null,
  attempt_count: 1,
  max_attempts: 2,
  started_at: iso(16 + (index % 7), 8 + index),
  completed_at: status === "running" ? null : iso(16 + (index % 7), 8 + index),
  created_at: iso(16 + (index % 7), 8 + index),
}));

export const demoFindings: SecurityFinding[] = [
  ["secret", "generic_api_key", "critical", "deny", "SECRET_DETECTED"],
  [
    "prompt_injection",
    "tool_override",
    "high",
    "require_approval",
    "PROMPT_INJECTION_REVIEW",
  ],
  ["pii", "email", "medium", "record", "PII_RECORDED"],
].map(([kind, category, severity, action, reason], index) => ({
  id: `80000000-0000-4000-8000-00000000000${index + 1}`,
  organization_id: org,
  decision_id: demoExecutions[index].decision_id,
  detector_id: `81000000-0000-4000-8000-00000000000${index + 1}`,
  detector_version_id: `82000000-0000-4000-8000-00000000000${index + 1}`,
  detector_kind: kind as SecurityFinding["detector_kind"],
  category: String(category),
  severity: severity as SecurityFinding["severity"],
  action: action as SecurityFinding["action"],
  reason_code: String(reason),
  location: "arguments.payload",
  occurrence_count: index + 1,
  created_at: iso(22, 13 + index),
}));

export const demoDetectors: SecurityDetector[] = demoFindings.map(
  (finding, index) => ({
    id: finding.detector_id,
    organization_id: org,
    name: ["Credential scanner", "Prompt guard", "PII monitor"][index],
    description: "Deterministic inspection before policy evaluation.",
    status: "active",
    priority: 10 + index * 10,
    current_version: 1,
    document: {
      kind: finding.detector_kind,
      action: finding.action,
      severity: finding.severity,
      reason_code: finding.reason_code,
    },
    created_by: demoUser.id,
    created_at: iso(12 + index),
    updated_at: iso(21 + index),
  }),
);

export const demoAudit: AuditEvent[] = demoExecutions
  .slice(0, 8)
  .map((execution, index) => ({
    id: `90000000-0000-4000-8000-00000000000${index + 1}`,
    organization_id: org,
    actor_type: index % 3 === 0 ? "system" : "agent",
    actor_id: index % 3 === 0 ? null : execution.agent_id,
    action: index % 2 === 0 ? "execution.succeeded" : "policy.evaluate",
    target_type: "tool_execution",
    target_id: execution.id,
    before_hash: null,
    after_hash: "7d6ed63c6a6b34f1",
    details_json: {},
    request_id: `req-demo-${index + 1}`,
    created_at: execution.created_at,
  }));

export function demoResponse(path: string, method: string): unknown {
  if (path === "/agents") return demoAgents;
  if (path === "/tools") return demoTools;
  if (path === "/policies") return demoPolicies;
  if (path.startsWith("/approvals")) {
    if (method === "POST") {
      const id = path.split("/")[2];
      const action = path.split("/")[3];
      const approval = demoApprovals.find((item) => item.id === id);
      return approval
        ? {
            ...approval,
            status: action === "approve" ? "approved" : "rejected",
          }
        : {};
    }
    return demoApprovals;
  }
  if (path === "/executions") return demoExecutions;
  if (path.startsWith("/security/findings")) return demoFindings;
  if (path === "/security/detectors") return demoDetectors;
  if (path === "/audit") return demoAudit;
  return [];
}
