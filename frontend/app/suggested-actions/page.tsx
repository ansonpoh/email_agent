"use client";

import { useState } from "react";

import { UserIdField } from "@/components/user-id-field";
import { approveAction, getPendingActions, PendingAction, rejectAction } from "@/lib/api";
import { useUserId } from "@/lib/use-user-id";

export default function SuggestedActionsPage() {
  const { userId, setUserId } = useUserId();
  const [actions, setActions] = useState<PendingAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadActions() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const rows = await getPendingActions(userId.trim());
      setActions(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load actions.");
    } finally {
      setLoading(false);
    }
  }

  async function resolveAction(actionId: string, decision: "approve" | "reject") {
    setError("");
    setMessage("");
    try {
      if (decision === "approve") {
        await approveAction(actionId);
      } else {
        await rejectAction(actionId);
      }
      setMessage(`Action ${decision}d.`);
      await loadActions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update action.");
    }
  }

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">Suggested Actions</h2>
        <p className="mt-1 text-sm text-slate-600">Review pending agent decisions and explicitly approve or reject.</p>
      </header>

      <div className="grid gap-3 rounded-lg border border-slate-200 p-4">
        <UserIdField userId={userId} onChange={setUserId} />
        <div>
          <button
            onClick={loadActions}
            disabled={loading}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {loading ? "Loading..." : "Load Pending Actions"}
          </button>
        </div>
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      </div>

      <div className="rounded-lg border border-slate-200">
        {actions.length === 0 ? (
          <p className="p-4 text-sm text-slate-600">No pending actions.</p>
        ) : (
          <ul className="divide-y divide-slate-200">
            {actions.map((action) => (
              <li key={action.id} className="space-y-2 p-4">
                <p className="text-sm text-slate-900">
                  <span className="font-medium">{action.action_type}</span> for email {action.email_id}
                </p>
                <p className="text-xs text-slate-500">Created: {new Date(action.created_at).toLocaleString()}</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => resolveAction(action.id, "approve")}
                    className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm text-white"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => resolveAction(action.id, "reject")}
                    className="rounded-md bg-rose-600 px-3 py-1.5 text-sm text-white"
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
