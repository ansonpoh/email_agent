"use client";

import { useState } from "react";

import { UserIdField } from "@/components/user-id-field";
import {
  createRule,
  deleteRule,
  getRules,
  linkTelegram,
  RuleItem,
  startGoogleAuth,
  startTelegramLink,
  testTelegram,
} from "@/lib/api";
import { useUserId } from "@/lib/use-user-id";

export default function SettingsPage() {
  const { userId, setUserId } = useUserId();
  const [rules, setRules] = useState<RuleItem[]>([]);
  const [ruleText, setRuleText] = useState("");
  const [stateValue, setStateValue] = useState("local-dev");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramLinkToken, setTelegramLinkToken] = useState("");
  const [telegramDeepLink, setTelegramDeepLink] = useState("");
  const [telegramMessage, setTelegramMessage] = useState("Telegram connectivity test from Gmail Agent Assistant.");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadRules() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const rows = await getRules(userId.trim());
      setRules(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load rules.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateRule() {
    if (!userId.trim() || !ruleText.trim()) {
      setError("User ID and rule text are required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await createRule(userId.trim(), ruleText.trim());
      setRuleText("");
      setMessage("Rule created.");
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create rule.");
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteRule(ruleId: string) {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await deleteRule(ruleId);
      setMessage("Rule deleted.");
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete rule.");
    } finally {
      setLoading(false);
    }
  }

  async function handleStartOauth() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await startGoogleAuth(stateValue || "local-dev");
      window.open(result.auth_url, "_blank", "noopener,noreferrer");
      setMessage("Opened Google OAuth in a new tab. Complete consent, then use returned user_id.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start OAuth.");
    } finally {
      setLoading(false);
    }
  }

  async function handleLinkTelegram() {
    if (!userId.trim() || !telegramChatId.trim()) {
      setError("User ID and Telegram chat ID are required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await linkTelegram(userId.trim(), telegramChatId.trim());
      setMessage("Telegram chat linked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to link Telegram.");
    } finally {
      setLoading(false);
    }
  }

  async function handleStartTelegramLink() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await startTelegramLink(userId.trim());
      setTelegramLinkToken(result.token);
      setTelegramDeepLink(result.deep_link ?? "");
      setMessage("Link token generated. Run /start <token> in Telegram.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate Telegram link token.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTelegramTest() {
    if (!userId.trim()) {
      setError("User ID is required.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await testTelegram(userId.trim(), telegramMessage);
      setMessage("Telegram test sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send Telegram test.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-5">
      <header>
        <h2 className="text-2xl font-semibold">User Rules & Settings</h2>
        <p className="mt-1 text-sm text-slate-600">Connect Gmail, manage rules, and validate Telegram delivery.</p>
      </header>

      <div className="grid gap-3 rounded-lg border border-slate-200 p-4">
        <UserIdField userId={userId} onChange={setUserId} />
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      </div>

      <div className="space-y-2 rounded-lg border border-slate-200 p-4">
        <p className="text-sm font-medium text-slate-900">Google OAuth</p>
        <input
          value={stateValue}
          onChange={(event) => setStateValue(event.target.value)}
          placeholder="OAuth state"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          onClick={handleStartOauth}
          disabled={loading}
          className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
        >
          Start Google OAuth
        </button>
      </div>

      <div className="space-y-2 rounded-lg border border-slate-200 p-4">
        <p className="text-sm font-medium text-slate-900">Rules</p>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={loadRules}
            disabled={loading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            Load Rules
          </button>
          <input
            value={ruleText}
            onChange={(event) => setRuleText(event.target.value)}
            placeholder="e.g., Prioritize emails from manager"
            className="min-w-72 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={handleCreateRule}
            disabled={loading}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            Add Rule
          </button>
        </div>
        {rules.length === 0 ? (
          <p className="text-sm text-slate-600">No rules loaded.</p>
        ) : (
          <ul className="space-y-2">
            {rules.map((rule) => (
              <li key={rule.id} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 p-2 text-sm">
                <span>{rule.rule_text}</span>
                <button
                  onClick={() => handleDeleteRule(rule.id)}
                  className="rounded-md bg-rose-600 px-2 py-1 text-xs text-white"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2 rounded-lg border border-slate-200 p-4">
        <p className="text-sm font-medium text-slate-900">Telegram</p>
        <button
          onClick={handleStartTelegramLink}
          disabled={loading}
          className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
        >
          Generate /start Link Token
        </button>
        {telegramLinkToken ? (
          <div className="rounded-md bg-slate-50 p-3 text-xs text-slate-700">
            <p>Token: {telegramLinkToken}</p>
            {telegramDeepLink ? <p className="mt-1">Deep link: {telegramDeepLink}</p> : null}
            <p className="mt-1">Use in Telegram chat: /start {telegramLinkToken}</p>
          </div>
        ) : null}
        <p className="text-xs text-slate-500">Legacy fallback: manual chat link.</p>
        <input
          value={telegramChatId}
          onChange={(event) => setTelegramChatId(event.target.value)}
          placeholder="Telegram chat id"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleLinkTelegram}
            disabled={loading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            Link Telegram Chat
          </button>
          <input
            value={telegramMessage}
            onChange={(event) => setTelegramMessage(event.target.value)}
            className="min-w-72 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={handleTelegramTest}
            disabled={loading}
            className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            Send Test
          </button>
        </div>
      </div>
    </section>
  );
}
