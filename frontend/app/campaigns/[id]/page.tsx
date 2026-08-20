import { notFound } from "next/navigation";

import { checkCampaignBacklinkAction, recordCampaignEventAction } from "@/app/actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Badge, EmptyState, Section } from "@/components/ui";
import { apiGet, ApiError } from "@/lib/api";
import { CAMPAIGN_FUNNEL_STAGES, type CampaignDetail } from "@/lib/types";

export default async function CampaignDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let campaign: CampaignDetail;
  try {
    campaign = await apiGet<CampaignDetail>(`/campaigns/${id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold break-all">{campaign.target_url}</h1>
        <p className="text-sm text-slate-500">
          Created {new Date(campaign.created_at).toLocaleString()} · Current stage:{" "}
          <Badge value={campaign.current_stage} />
        </p>
      </div>

      <Section title="Record a funnel event">
        <p className="mb-3 text-sm text-slate-500">
          This app never sends anything itself -- log what actually happened after you pitched
          this asset through your own email client.
        </p>
        <form action={recordCampaignEventAction} className="flex flex-wrap items-end gap-2">
          <input type="hidden" name="campaign_id" value={id} />
          <select name="stage" required className="rounded border border-slate-300 px-3 py-1.5 text-sm">
            {CAMPAIGN_FUNNEL_STAGES.map((stage) => (
              <option key={stage} value={stage}>
                {stage.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <input
            name="detail"
            placeholder="Optional detail"
            className="w-64 rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <SubmitButton pendingLabel="Recording…">Record event</SubmitButton>
        </form>

        <form action={checkCampaignBacklinkAction} className="mt-3">
          <input type="hidden" name="campaign_id" value={id} />
          <SubmitButton pendingLabel="Checking…" variant="secondary">
            Check for a real backlink now
          </SubmitButton>
        </form>
      </Section>

      <Section title={`Funnel history (${campaign.events.length})`}>
        {campaign.events.length === 0 ? (
          <EmptyState>No events recorded yet.</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Stage</th>
                <th>Detail</th>
                <th>Occurred</th>
              </tr>
            </thead>
            <tbody>
              {campaign.events.map((e) => (
                <tr key={e.id}>
                  <td>
                    <Badge value={e.stage} />
                  </td>
                  <td>{e.detail ?? <span className="text-slate-400">—</span>}</td>
                  <td>{new Date(e.occurred_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}
