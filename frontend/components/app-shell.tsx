import Link from "next/link";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/emails-summary", label: "Emails Summary" },
  { href: "/suggested-actions", label: "Suggested Actions" },
  { href: "/draft-review", label: "Draft Review" },
  { href: "/settings", label: "Rules & Settings" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Personal Gmail Assistant</p>
            <h1 className="text-lg font-semibold">Agent Console</h1>
          </div>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800">
            Manual send only
          </span>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-6 sm:grid-cols-[230px_1fr] sm:px-6">
        <aside className="rounded-xl border border-slate-200 bg-white p-3">
          <nav className="space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="rounded-xl border border-slate-200 bg-white p-5">{children}</main>
      </div>
    </div>
  );
}
