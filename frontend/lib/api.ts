export type HealthResponse = {
  status: string;
};

export type EmailSummaryItem = {
  id: number;
  subject: string;
  sender_email: string;
  received_at: string;
  is_read: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API request failed (${response.status}): ${text}`);
  }

  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export async function getEmails(userId: number): Promise<EmailSummaryItem[]> {
  const payload = await apiFetch<{ items: EmailSummaryItem[] }>(`/emails?user_id=${userId}`);
  return payload.items;
}

export async function syncEmails(userId: number): Promise<{ synced: number; last_checked_at: string }> {
  return apiFetch<{ synced: number; last_checked_at: string }>("/emails/sync", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}
