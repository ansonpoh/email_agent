export default function DashboardPage() {
  const cards = [
    {
      title: "Primary interface",
      value: "Telegram",
      description: "Use /sync, /digest, /pending and inline approval buttons from Telegram.",
    },
    {
      title: "Automation",
      value: "Hourly",
      description: "Celery beat runs hourly sync + analysis + digest for linked Telegram users.",
    },
    {
      title: "This web app",
      value: "Setup/Status",
      description: "Use this UI for OAuth, Telegram linking, and operational checks.",
    },
  ];

  return (
    <section className="space-y-5">
      <header>
        <h2 className="text-2xl font-semibold">Status Dashboard</h2>
        <p className="mt-1 text-sm text-slate-600">
          Telegram is the primary control plane. This page summarizes operational mode and safety guarantees.
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
