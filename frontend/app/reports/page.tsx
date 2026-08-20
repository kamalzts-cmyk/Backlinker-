import { Section } from "@/components/ui";
import { EXPORT_FORMATS, REPORT_TYPES } from "@/lib/types";

export default function ReportsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Reports</h1>
        <p className="text-sm text-slate-500">
          Every value in every report traces back to a row an engine already collected and
          verified -- this page only formats what exists.
        </p>
      </div>

      <Section title="Export a report">
        <form action="/reports/download" method="get" className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs text-slate-500">Report type</label>
            <select name="type" required className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm">
              {REPORT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500">Format</label>
            <select name="format" required defaultValue="csv" className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm">
              {EXPORT_FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <p className="text-xs text-slate-500 sm:col-span-2">
            Fill in only the domain ID(s) your chosen report type needs (find one on a domain
            detail page&apos;s URL): <code>domain_id</code> for contacts/guest_posts/
            opportunity_scores, <code>primary_domain_id</code> for link_gaps,{" "}
            <code>target_domain_id</code>/<code>source_domain_id</code> for backlinks,{" "}
            <code>reference_domain_id</code> optionally for opportunity_scores.
          </p>

          <div>
            <label className="block text-xs text-slate-500">domain_id</label>
            <input name="domain_id" className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500">primary_domain_id</label>
            <input name="primary_domain_id" className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500">target_domain_id</label>
            <input name="target_domain_id" className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500">source_domain_id</label>
            <input name="source_domain_id" className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500">reference_domain_id</label>
            <input name="reference_domain_id" className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm" />
          </div>

          <div className="sm:col-span-2">
            <button
              type="submit"
              className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              Download
            </button>
          </div>
        </form>
      </Section>
    </div>
  );
}
