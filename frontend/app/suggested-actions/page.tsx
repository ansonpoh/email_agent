export default function SuggestedActionsPage() {
  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-2xl font-semibold">Suggested Actions</h2>
        <p className="mt-1 text-sm text-slate-600">
          Shows pending agent actions that require explicit user approval.
        </p>
      </header>

      <div className="rounded-lg border border-slate-200 p-4">
        <p className="text-sm text-slate-700">Backend integration target:</p>
        <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
          <li>`GET /actions/pending`</li>
          <li>`POST /actions/{'{action_id}'}/approve`</li>
          <li>`POST /actions/{'{action_id}'}/reject`</li>
        </ul>
      </div>
    </section>
  );
}
