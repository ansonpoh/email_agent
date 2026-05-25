"use client";

import { useState } from "react";

import { UserIdField } from "@/components/user-id-field";
import { createDraftInGmail, EmailSummaryItem, generateDraft, getEmails } from "@/lib/api";
import { useUserId } from "@/lib/use-user-id";

export default function DraftReviewPage() {
  const { userId, setUserId } = useUserId();
  const [emails, setEmails] = useState<EmailSummaryItem[]>([]);
  const [selectedEmailId, setSelectedEmailId] = useState("");
  const [tone, setTone] = useState("professional");
  const [draftId, setDraftId] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [gmailDraftId, setGmailDraftId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadEmails() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const rows = await getEmails(userId.trim());
      setEmails(rows);
      if (rows.length && !selectedEmailId) {
        setSelectedEmailId(rows[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load emails.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateDraft() {
    if (!selectedEmailId) {
      setError("Select an email first.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    setGmailDraftId("");
    try {
      const result = await generateDraft(selectedEmailId, tone);
      setDraftId(result.draft_id);
      setDraftBody(result.output.body);
      setMessage("Draft generated. Review before creating it in Gmail.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Draft generation failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateInGmail() {
    if (!draftId) {
      setError("Generate a draft first.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await createDraftInGmail(draftId);
      setGmailDraftId(result.gmail_draft_id);
      setMessage("Draft created in Gmail. Sending must be done manually in Gmail.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create draft in Gmail.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">Draft Review</h2>
        <p className="mt-1 text-sm text-slate-600">
          Generate a reply draft, review it, then create a Gmail draft. Sending is always manual.
        </p>
      </header>

      <div className="grid gap-3 rounded-lg border border-slate-200 p-4">
        <UserIdField userId={userId} onChange={setUserId} />
        <div className="flex gap-2">
          <button
            onClick={loadEmails}
            disabled={loading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-60"
          >
            Load Emails
          </button>
          <select
            value={tone}
            onChange={(event) => setTone(event.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="professional">Professional</option>
            <option value="friendly">Friendly</option>
          </select>
        </div>
        {emails.length > 0 ? (
          <select
            value={selectedEmailId}
            onChange={(event) => setSelectedEmailId(event.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {emails.map((email) => (
              <option key={email.id} value={email.id}>
                {email.subject || "(No subject)"} - {email.sender_email}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-slate-600">No emails loaded yet.</p>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleGenerateDraft}
            disabled={loading}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            Generate Draft
          </button>
          <button
            onClick={handleCreateInGmail}
            disabled={loading || !draftId}
            className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            Create in Gmail
          </button>
        </div>
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      </div>

      {draftBody ? (
        <div className="rounded-lg border border-slate-200 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Draft Body</p>
          <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{draftBody}</pre>
          {gmailDraftId ? (
            <p className="mt-3 text-sm text-emerald-700">Gmail draft created: {gmailDraftId}</p>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Auto-send is intentionally not supported. Final send must be completed by the user in Gmail.
      </div>
    </section>
  );
}
