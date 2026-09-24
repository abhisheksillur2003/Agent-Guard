export type RiskTier = "low" | "medium" | "high" | "critical";
export type AgentStatus = "active" | "suspended" | "revoked";
export type ExecutionStatus =
  | "authorized"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "timed_out"
  | "cancelled";

export interface CurrentUser {
  id: string;
  organization_id: string;
  email: string;
  role: "admin" | "developer" | "approver" | "read_only";
  status: "active" | "disabled";
  created_at: string;
  last_login_at: string | null;
}

export interface ReliabilityBudget {
  max_decisions_per_minute: number;
  max_executions_per_day: number;
  max_identical_requests_in_window: number;
  loop_detection_window_seconds: number;
  max_execution_attempts: number;
  retry_backoff_seconds: number;
}

export interface Agent {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  owner_user_id: string | null;
  status: AgentStatus;
  risk_tier: RiskTier;
  allowed_environments: string[];
  budget_config: ReliabilityBudget;
  created_at: string;
  updated_at: string;
}

export interface Tool {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  risk_class: RiskTier;
  capability_flags: string[];
  status: "active" | "disabled";
  adapter_name: string;
  adapter_version: string;
  execution_timeout_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface AgentCredential {
  credential: string;
  key_prefix: string;
  expires_at: string | null;
  warning: string;
}

export interface AgentPermission {
  id: string;
  agent_id: string;
  tool_id: string;
  operations: string[];
  constraints_json: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Policy {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: "active" | "disabled";
  priority: number;
  current_version: number;
  document: {
    scope: {
      agent_ids: string[];
      tool_ids: string[];
      environments: string[];
      operations: string[];
    };
    effect: "deny" | "require_approval";
    reason_code: string;
    conditions: Array<Record<string, unknown>>;
  };
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Approval {
  id: string;
  organization_id: string;
  decision_id: string;
  agent_id: string;
  requested_tool_id: string;
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled";
  expires_at: string;
  decided_at: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Execution {
  id: string;
  organization_id: string;
  decision_id: string;
  approval_id: string | null;
  agent_id: string;
  tool_id: string;
  operation: string;
  environment: string;
  status: ExecutionStatus;
  adapter_name: string;
  adapter_version: string;
  result_summary: Record<string, unknown>;
  error_code: string | null;
  attempt_count: number;
  max_attempts: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface SecurityFinding {
  id: string;
  organization_id: string;
  decision_id: string;
  detector_id: string;
  detector_version_id: string;
  detector_kind: "secret" | "pii" | "prompt_injection";
  category: string;
  severity: RiskTier;
  action: "record" | "require_approval" | "deny";
  reason_code: string;
  location: string;
  occurrence_count: number;
  created_at: string;
}

export interface SecurityDetector {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: "active" | "disabled";
  priority: number;
  current_version: number;
  document: {
    kind: string;
    action: string;
    severity: RiskTier;
    reason_code: string;
  };
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  organization_id: string;
  actor_type: "user" | "agent" | "system";
  actor_id: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  before_hash: string | null;
  after_hash: string | null;
  details_json: Record<string, unknown>;
  request_id: string | null;
  created_at: string;
}

export interface LocalAIStatus {
  available: boolean;
  model: string;
  model_available: boolean;
  installed_models: string[];
  advisory_only: true;
}

export interface LocalAIClassification {
  risk_level: RiskTier;
  confidence: number;
  categories: string[];
  rationale: string;
  model: string;
  advisory_only: true;
}
