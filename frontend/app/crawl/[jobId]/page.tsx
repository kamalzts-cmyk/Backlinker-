import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, Section } from "@/components/ui";
import { apiGet, ApiError } from "@/lib/api";
import type { CrawlJobDetail } from "@/lib/types";

export default async function CrawlJobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;

  let job: CrawlJobDetail;
  try {
    job = await apiGet<CrawlJobDetail>(`/crawl/${jobId}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Crawl job</h1>
        <p className="text-sm text-slate-500">{job.start_url}</p>
      </div>

      <Section title="Status">
        <dl className="grid grid-cols-2 gap-y-2 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-slate-500">Status</dt>
            <dd>
              <Badge value={job.status} />
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Pages crawled</dt>
            <dd>{job.pages_crawled}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Pages recorded</dt>
            <dd>{job.page_count}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Errors</dt>
            <dd>{job.error_count}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Max pages</dt>
            <dd>{job.max_pages}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Started</dt>
            <dd>{job.started_at ? new Date(job.started_at).toLocaleString() : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Finished</dt>
            <dd>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}</dd>
          </div>
        </dl>
        <p className="mt-4 text-sm">
          <Link href={`/domains/${job.domain_id}`} className="text-slate-700 hover:underline">
            ← back to domain
          </Link>
        </p>
      </Section>
    </div>
  );
}
