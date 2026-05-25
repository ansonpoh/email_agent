"use client";

import { useState } from "react";

import { UserIdField } from "@/components/user-id-field";
import { analyseEmail, EmailAnalysisOutput, EmailSummaryItem, getEmails, syncEmails } from "@/lib/api";
import { useUserId } from "@/lib/use-user-id";

export default function EmailsSummaryPage() {
  const { userId, setUserId } = useUserId();
  const [emails, setEmails] = useState<EmailSummaryItem[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, EmailAnalysisOutput>>({});
  const [loading, setLoading] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [error, setError] = useState("");

  async function loadEmails() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const rows = await getEmails(userId.trim());
      setEmails(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load emails.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSync() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }

    setLoading(true);
    setError("");
    setSyncMessage("");
    try {
      const result = await syncEmails(userId.trim());
      setSyncMessage(`Synced ${result.synced}/${result.fetched} emails.`);
      await loadEmails();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze(emailId: string) {
    setError("");
    try {
      const result = await analyseEmail(emailId);
      setAnalyses((prev) => ({ ...prev, [emailId]: result.analysis }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
    }
  }

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">Emails Summary</h2>
        <p className="mt-1 text-sm text-slate-600">Sync inbox data, list stored emails, and run structured analysis.</p>
      </header>

      <div className="grid gap-3 rounded-lg border border-slate-200 p-4">
        <UserIdField userId={userId} onChange={setUserId} />
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleSync}
            disabled={loading}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {loading ? "Working..." : "Sync Emails"}
          </button>
          <button
            onClick={loadEmails}
            disabled={loading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-60"
          >
            Refresh List
          </button>
        </div>
        {syncMessage ? <p className="text-sm text-emerald-700">{syncMessage}</p> : null}
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      </div>

      <div className="rounded-lg border border-slate-200">
        {emails.length === 0 ? (
          <p className="p-4 text-sm text-slate-600">No emails loaded yet.</p>
        ) : (
          <ul className="divide-y divide-slate-200">
            {emails.map((email) => {
              const analysis = analyses[email.id];
              return (
                <li key={email.id} className="space-y-2 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium text-slate-900">{email.subject || "(No subject)"}</p>
                      <p className="text-xs text-slate-500">
                        {email.sender_email} • {new Date(email.received_at).toLocaleString()}
                      </p>
                    </div>
                    <button
                      onClick={() => handleAnalyze(email.id)}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
                    >
                      Analyze
                    </button>
                  </div>

                  {analysis ? (
                    <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
                      <p>
                        <span className="font-medium">Category:</span> {analysis.category}
                      </p>
                      <p>
                        <span className="font-medium">Priority:</span> {analysis.priority_score}/5
                      </p>
                      <p className="mt-1">{analysis.summary}</p>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
