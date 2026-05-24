export default function SettingsPage() {
  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">User Rules & Settings</h2>
        <p className="mt-1 text-sm text-slate-600">
          Configure Gmail OAuth, Telegram link, and user-specific processing rules.
        </p>
      </header>

      <div className="rounded-lg border border-slate-200 p-4">
        <p className="text-sm text-slate-700">Backend integration target:</p>
        <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
          <li>`POST /auth/google/start` and `GET /auth/google/callback`</li>
          <li>`GET /rules`, `POST /rules`, `DELETE /rules/{'{rule_id}'}`</li>
          <li>`POST /telegram/link`, `POST /telegram/test`</li>
        </ul>
      </div>
    </section>
  );
}
