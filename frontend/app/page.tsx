export default function DashboardPage() {
  const cards = [
    {
      title: "Inbox sync",
      value: "Ready",
      description: "Sync emails since the last check-in with /emails/sync.",
    },
    {
      title: "AI analysis",
      value: "Placeholder",
      description: "Summaries, priority score, tasks and deadlines are generated per email.",
    },
    {
      title: "Telegram digest",
      value: "Manual trigger",
      description: "Generate digest first, then send to Telegram via explicit endpoint call.",
    },
  ];

  return (
    <section className="space-y-5">
      <header>
        <h2 className="text-2xl font-semibold">Dashboard</h2>
        <p className="mt-1 text-sm text-slate-600">
          MVP control panel for Gmail-only ingestion, AI-assisted triage, and manual review workflows.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <article key={card.title} className="rounded-lg border border-slate-200 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">{card.title}</p>
            <p className="mt-2 text-lg font-semibold text-slate-900">{card.value}</p>
            <p className="mt-2 text-sm text-slate-600">{card.description}</p>
          </article>
        ))}
      </div>

      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        Safety guardrail: this system does not provide any email send endpoint and never auto-sends emails.
      </div>
    </section>
  );
}
