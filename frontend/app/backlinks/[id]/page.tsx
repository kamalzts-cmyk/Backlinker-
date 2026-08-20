import { notFound } from "next/navigation";

import { recheckBacklinkAction } from "@/app/actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Badge, EmptyState, Section } from "@/components/ui";
import { apiGet, ApiError } from "@/lib/api";
import type { BacklinkDetail, BacklinkMonitoringEvent } from "@/lib/types";

export default async function BacklinkDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let backlink: BacklinkDetail;
  try {
    backlink = await apiGet<BacklinkDetail>(`/backlinks/${id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const monitoringEvents = await apiGet<BacklinkMonitoringEvent[]>(
    `/backlinks/${id}/monitoring-events`
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold break-all">{backlink.source_url}</h1>
        <p className="text-sm text-slate-500 break-all">→ {backlink.target_url}</p>
      </div>

      <Section
        title="Monitor"
        action={
          <form action={recheckBacklinkAction}>
            <input type="hidden" name="backlink_id" value={id} />
            <SubmitButton pendingLabel="Rechecking…" variant="secondary">
              Recheck now
            </SubmitButton>
          </form>
        }
      >
        <p className="mb-3 text-sm text-slate-500">
          First seen {new Date(backlink.first_seen_at).toLocaleString()} · Last seen{" "}
          {new Date(backlink.last_seen_at).toLocaleString()}
        </p>
        {monitoringEvents.length === 0 ? (
          <EmptyState>No changes detected since first verified.</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Change</th>
                <th>Detail</th>
                <th>Detected</th>
              </tr>
            </thead>
            <tbody>
              {monitoringEvents.map((e) => (
                <tr key={e.id}>
                  <td>
                    <Badge value={e.change_type} />
                  </td>
                  <td>{e.detail}</td>
                  <td>{new Date(e.detected_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`Observation history (${backlink.observations.length})`}>
        <table>
          <thead>
            <tr>
              <th>Anchor</th>
              <th>Type</th>
              <th>Rel</th>
              <th>Confidence</th>
              <th>Observed</th>
            </tr>
          </thead>
          <tbody>
            {backlink.observations.map((o) => (
              <tr key={o.id}>
                <td>{o.anchor_text || <span className="text-slate-400">—</span>}</td>
                <td>
                  <Badge value={o.link_type} />
                </td>
                <td className="space-x-1">
                  {o.rel_nofollow && <Badge value="nofollow" />}
                  {o.rel_sponsored && <Badge value="sponsored" />}
                  {o.rel_ugc && <Badge value="ugc" />}
                  {!o.rel_nofollow && !o.rel_sponsored && !o.rel_ugc && (
                    <span className="text-slate-400">follow</span>
                  )}
                </td>
                <td>{o.confidence_score}</td>
                <td>{new Date(o.observed_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
