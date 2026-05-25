"use client";

type Props = {
  userId: string;
  onChange: (value: string) => void;
};

export function UserIdField({ userId, onChange }: Props) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium uppercase tracking-wide text-slate-500">User ID</span>
      <input
        value={userId}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Paste user UUID from OAuth callback response"
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none ring-blue-200 focus:ring"
      />
    </label>
  );
}
