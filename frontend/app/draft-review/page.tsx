export default function DraftReviewPage() {
  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">Draft Review</h2>
        <p className="mt-1 text-sm text-slate-600">
          Generate draft replies for review and optionally create Gmail drafts without sending.
        </p>
      </header>

      <div className="rounded-lg border border-slate-200 p-4">
        <p className="text-sm text-slate-700">Backend integration target:</p>
        <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
          <li>`POST /drafts/generate`</li>
          <li>`POST /drafts/{'{draft_id}'}/create-in-gmail`</li>
        </ul>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Drafts are user-reviewed and user-sent in Gmail. Auto-send is intentionally not supported.
      </div>
    </section>
  );
}
