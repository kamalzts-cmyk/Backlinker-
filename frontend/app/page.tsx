import Link from "next/link";

import { registerDomainAction } from "@/app/actions";
import { SubmitButton } from "@/components/SubmitButton";
import { EmptyState } from "@/components/ui";
import { apiGet } from "@/lib/api";
import type { Domain } from "@/lib/types";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const domains = await apiGet<Domain[]>("/domains", { q });

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h1 className="text-base font-semibold">Register a domain</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every crawl, backlink check, or competitor relationship starts from a registered
          domain.
        </p>
        <form action={registerDomainAction} className="mt-3 flex gap-2">
          <input
            name="host"
            required
            placeholder="example.com"
            className="flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <SubmitButton pendingLabel="Registering…">Register</SubmitButton>
        </form>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-base font-semibold">Domains</h1>
          <form className="flex gap-2">
            <input
              name="q"
              defaultValue={q ?? ""}
              placeholder="Search hosts…"
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              Search
            </button>
          </form>
        </div>

        {domains.length === 0 ? (
          <div className="mt-4">
            <EmptyState>
              {q ? `No domains match "${q}".` : "No domains registered yet."}
            </EmptyState>
          </div>
        ) : (
          <table className="mt-3">
            <thead>
              <tr>
                <th>Host</th>
                <th>First seen</th>
                <th>Last crawled</th>
              </tr>
            </thead>
            <tbody>
              {domains.map((domain) => (
                <tr key={domain.id}>
                  <td>
                    <Link href={`/domains/${domain.id}`} className="font-medium text-slate-900 hover:underline">
                      {domain.normalized_host}
                    </Link>
                  </td>
                  <td>{new Date(domain.first_seen_at).toLocaleString()}</td>
                  <td>
                    {domain.last_crawled_at ? (
                      new Date(domain.last_crawled_at).toLocaleString()
                    ) : (
                      <span className="text-slate-400">never</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
