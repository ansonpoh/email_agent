export type HealthResponse = {
  status: string;
};

export type EmailSummaryItem = {
  id: string;
  subject: string | null;
  sender_email: string;
  received_at: string;
  is_read: boolean;
};

export type EmailAnalysisOutput = {
  category: string;
  priority_score: number;
  summary: string;
  key_points: string[];
  extracted_tasks: string[];
  extracted_deadlines: string[];
  suggested_action: string;
  confidence_score: number;
};

export type PendingAction = {
  id: string;
  email_id: string;
  action_type: string;
  status: string;
  suggested_payload: Record<string, unknown>;
  requires_approval: boolean;
  execution_payload?: Record<string, unknown>;
  execution_error?: string | null;
  created_at: string;
};

export type RuleItem = {
  id: string;
  user_id: string;
  rule_text: string;
  is_active: boolean;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;
  requestId?: string;

  constructor(status: number, detail: string, requestId?: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail ?? `API request failed (${response.status})`;
    throw new ApiError(response.status, String(detail), data?.request_id);
  }

  return data as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export async function getEmails(userId: string): Promise<EmailSummaryItem[]> {
  const payload = await apiFetch<{ items: EmailSummaryItem[] }>(`/emails?user_id=${userId}`);
  return payload.items;
}

export async function syncEmails(userId: string): Promise<{ synced: number; fetched: number; last_checked_at: string }> {
  return apiFetch<{ synced: number; fetched: number; last_checked_at: string }>("/emails/sync", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function analyseEmail(emailId: string): Promise<{ email_id: string; analysis: EmailAnalysisOutput }> {
  return apiFetch<{ email_id: string; analysis: EmailAnalysisOutput }>(`/emails/${emailId}/analyse`, {
    method: "POST",
  });
}

export async function getPendingActions(userId: string): Promise<PendingAction[]> {
  const payload = await apiFetch<{ items: PendingAction[] }>(`/actions/pending?user_id=${userId}`);
  return payload.items;
}

export async function approveAction(
  actionId: string,
): Promise<{ action_id: string; status: string; execution: Record<string, unknown> }> {
  return apiFetch<{ action_id: string; status: string; execution: Record<string, unknown> }>(`/actions/${actionId}/approve`, {
    method: "POST",
  });
}

export async function rejectAction(
  actionId: string,
): Promise<{ action_id: string; status: string; execution: Record<string, unknown> }> {
  return apiFetch<{ action_id: string; status: string; execution: Record<string, unknown> }>(`/actions/${actionId}/reject`, {
    method: "POST",
  });
}

export async function generateDraft(emailId: string, tone: string): Promise<{ draft_id: string; output: { body: string; tone: string } }> {
  return apiFetch<{ draft_id: string; output: { body: string; tone: string } }>("/drafts/generate", {
    method: "POST",
    body: JSON.stringify({ email_id: emailId, tone }),
  });
}

export async function createDraftInGmail(
  draftId: string,
): Promise<{ draft_id: string; gmail_draft_id: string; note: string; created_at: string }> {
  return apiFetch<{ draft_id: string; gmail_draft_id: string; note: string; created_at: string }>(
    `/drafts/${draftId}/create-in-gmail`,
    { method: "POST" },
  );
}

export async function getRules(userId: string): Promise<RuleItem[]> {
  const payload = await apiFetch<{ items: RuleItem[] }>(`/rules?user_id=${userId}`);
  return payload.items;
}

export async function createRule(userId: string, ruleText: string): Promise<RuleItem> {
  return apiFetch<RuleItem>("/rules", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, rule_text: ruleText }),
  });
}

export async function deleteRule(ruleId: string): Promise<{ deleted: boolean; rule_id: string }> {
  return apiFetch<{ deleted: boolean; rule_id: string }>(`/rules/${ruleId}`, { method: "DELETE" });
}

export async function startGoogleAuth(state: string): Promise<{ auth_url: string; state: string }> {
  return apiFetch<{ auth_url: string; state: string }>("/auth/google/start", {
    method: "POST",
    body: JSON.stringify({ state }),
  });
}

export async function linkTelegram(
  userId: string,
  telegramChatId: string,
): Promise<{ linked: boolean; telegram_chat_id: string }> {
  return apiFetch<{ linked: boolean; telegram_chat_id: string }>("/telegram/link", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, telegram_chat_id: telegramChatId }),
  });
}

export async function startTelegramLink(
  userId: string,
): Promise<{ ok: boolean; token: string; deep_link: string | null; expires_at: string }> {
  return apiFetch<{ ok: boolean; token: string; deep_link: string | null; expires_at: string }>("/telegram/link/start", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function testTelegram(
  userId: string,
  message: string,
): Promise<{ ok: boolean; sent: boolean }> {
  return apiFetch<{ ok: boolean; sent: boolean }>("/telegram/test", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, message }),
  });
}
