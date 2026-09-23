"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusPill,
} from "@/components/ui";
import { apiGet, apiPost } from "@/lib/api-client";
import { formatDate, shortId } from "@/lib/format";
import type { Approval } from "@/lib/types";

export function ApprovalsView() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Approval | null>(null);
  const [reason, setReason] = useState("");
  const query = useQuery({
    queryKey: ["approvals"],
    queryFn: () => apiGet<Approval[]>("/approvals"),
  });
  const mutation = useMutation({
    mutationFn: ({
      approval,
      action,
    }: {
      approval: Approval;
      action: "approve" | "reject";
    }) => apiPost<Approval>(`/approvals/${approval.id}/${action}`, { reason }),
    onSuccess: async () => {
      setSelected(null);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
  return (
    <>
      <PageHeader
        eyebrow="Human in the loop"
        title="Approvals"
        description="Review high-impact requests before the agent receives execution authority."
      />
      {query.isLoading ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : !query.data?.length ? (
        <EmptyState
          title="Approval queue is clear"
          message="Requests requiring human review will appear here."
        />
      ) : (
        <div className="approval-layout">
          <Panel
            title="Approval queue"
            subtitle={`${query.data.filter((item) => item.status === "pending").length} decisions need attention`}
          >
            <div className="approval-list">
              {query.data.map((approval) => (
                <button
                  key={approval.id}
                  className={selected?.id === approval.id ? "selected" : ""}
                  onClick={() => {
                    setSelected(approval);
                    setReason("");
                  }}
                >
                  <span className="approval-icon">
                    <ShieldAlert size={18} />
                  </span>
                  <span>
                    <strong>
                      Tool request {shortId(approval.decision_id)}
                    </strong>
                    <small>
                      Agent {shortId(approval.agent_id)} · expires{" "}
                      {formatDate(approval.expires_at)}
                    </small>
                  </span>
                  <StatusPill value={approval.status} />
                </button>
              ))}
            </div>
          </Panel>
          <Panel
            title="Decision review"
            subtitle="Confirm context before recording a final action"
          >
            {selected ? (
              <div className="approval-review">
                <dl>
                  <div>
                    <dt>Decision</dt>
                    <dd className="mono">{selected.decision_id}</dd>
                  </div>
                  <div>
                    <dt>Agent</dt>
                    <dd className="mono">{selected.agent_id}</dd>
                  </div>
                  <div>
                    <dt>Requested tool</dt>
                    <dd className="mono">{selected.requested_tool_id}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <StatusPill value={selected.status} />
                    </dd>
                  </div>
                  <div>
                    <dt>Expires</dt>
                    <dd>{formatDate(selected.expires_at)}</dd>
                  </div>
                </dl>
                {selected.status === "pending" && (
                  <>
                    <label className="reason-field">
                      Decision reason
                      <textarea
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                        placeholder="Record why this action is safe or should be blocked"
                        maxLength={2000}
                      />
                    </label>
                    {mutation.error && (
                      <p className="form-error">{mutation.error.message}</p>
                    )}
                    <div className="approval-actions">
                      <button
                        className="secondary-button reject"
                        disabled={
                          reason.trim().length < 3 || mutation.isPending
                        }
                        onClick={() =>
                          mutation.mutate({
                            approval: selected,
                            action: "reject",
                          })
                        }
                      >
                        <X size={17} />
                        Reject
                      </button>
                      <button
                        className="primary-button"
                        disabled={
                          reason.trim().length < 3 || mutation.isPending
                        }
                        onClick={() =>
                          mutation.mutate({
                            approval: selected,
                            action: "approve",
                          })
                        }
                      >
                        <Check size={17} />
                        Approve
                      </button>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <EmptyState
                title="Select a request"
                message="Choose a queued request to inspect its authorization context."
              />
            )}
          </Panel>
        </div>
      )}
    </>
  );
}
