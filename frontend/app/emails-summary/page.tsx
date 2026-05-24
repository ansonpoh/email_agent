export default function EmailsSummaryPage() {
  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">Emails Summary</h2>
        <p className="mt-1 text-sm text-slate-600">
          Placeholder view for recent emails, extracted summaries, categories, and priority scores.
        </p>
      </header>

      <div className="rounded-lg border border-slate-200 p-4">
        <p className="text-sm text-slate-700">Backend integration target:</p>
        <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
          <li>`POST /emails/sync` to fetch from Gmail since last check-in</li>
          <li>`GET /emails` to list inbox records</li>
          <li>`POST /emails/{'{email_id}'}/analyse` to run structured analysis</li>
        </ul>
      </div>
    </section>
  );
}
