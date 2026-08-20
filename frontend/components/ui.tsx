// Small shared presentation primitives. Deliberately not a design
// system -- dense data tables and evidence panels over marketing-style
// cards, per docs/ARCHITECTURE.md §4.

export function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-slate-500">{children}</p>;
}

const BADGE_TONES: Record<string, string> = {
  measured: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  cited: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  verified: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  directly_published: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  high: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  low: "bg-amber-50 text-amber-700 ring-amber-600/20",
  medium: "bg-blue-50 text-blue-700 ring-blue-600/20",
  unavailable: "bg-slate-100 text-slate-500 ring-slate-500/20",
  unknown: "bg-slate-100 text-slate-500 ring-slate-500/20",
  not_cited: "bg-slate-100 text-slate-500 ring-slate-500/20",
  invalid: "bg-red-50 text-red-700 ring-red-600/20",
  failed: "bg-red-50 text-red-700 ring-red-600/20",
  lost: "bg-red-50 text-red-700 ring-red-600/20",
  rejected: "bg-red-50 text-red-700 ring-red-600/20",
};

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const tone = BADGE_TONES[value] ?? "bg-slate-100 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function EvidenceList({ evidence }: { evidence: string[] }) {
  if (evidence.length === 0) return <EmptyState>No evidence recorded.</EmptyState>;
  return (
    <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
      {evidence.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </div>
  );
}
