import Link from "next/link";

import { discoverProspectsAction } from "@/app/actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Badge, EmptyState, EvidenceList, Section } from "@/components/ui";
import { apiGet } from "@/lib/api";
import type { Prospect } from "@/lib/types";

export default async function ProspectsPage({
  searchParams,
}: {
  searchParams: Promise<{ topic?: string }>;
}) {
  const { topic } = await searchParams;
  const prospects = topic ? await apiGet<Prospect[]>("/prospects", { topic }) : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Prospect discovery</h1>
        <p className="text-sm text-slate-500">
          Independent discovery of topically relevant sites (resource pages, roundups, guest-post
          blogs, industry publications) via Claude&apos;s web search tool -- not just
          competitor-derived. <code>topical_fit_score</code> is a crude keyword-overlap proxy;
          for a real comparison against your own crawled content, run a domain&apos;s opportunity
          score with a reference domain.
        </p>
      </div>

      <Section title="Discover">
        <form action={discoverProspectsAction} className="flex flex-wrap items-end gap-2">
          <div className="flex-1">
            <label className="block text-xs text-slate-500">Topic</label>
            <input
              name="topic"
              required
              defaultValue={topic ?? ""}
              placeholder="e.g. project management software"
              className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <SubmitButton pendingLabel="Searching…">Discover prospects</SubmitButton>
        </form>
      </Section>

      <Section title={topic ? `Prospects for "${topic}"` : "Prospects"}>
        {!topic ? (
          <EmptyState>Enter a topic above to discover prospects.</EmptyState>
        ) : prospects.length === 0 ? (
          <EmptyState>No prospects found for &quot;{topic}&quot; yet.</EmptyState>
        ) : (
          <div className="space-y-3">
            {prospects.map((p) => (
              <div key={p.id} className="rounded border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/domains/${p.domain_id}`} className="font-medium hover:underline">
                    {p.domain_host}
                  </Link>
                  <Badge value={p.category} />
                  <span className="text-slate-500">fit score: {p.topical_fit_score}/100</span>
                </div>
                <p className="mt-1 break-all text-slate-500">{p.source_url}</p>
                <div className="mt-2">
                  <EvidenceList evidence={p.evidence} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
