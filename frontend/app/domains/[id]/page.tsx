import { notFound } from "next/navigation";

import {
  addCompetitorAction,
  computeOpportunityScoreAction,
  createCampaignAction,
  discoverContactsAction,
  discoverGuestPostAction,
  generateOutreachStrategyAction,
  recordGeoObservationAction,
  runCrawlAction,
  verifyEmailAction,
} from "@/app/actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Badge, EmptyState, EvidenceList, Section } from "@/components/ui";
import { apiGet, apiGetOrNull, apiPost, ApiError } from "@/lib/api";
import {
  GEO_CITATION_RESULTS,
  type Backlink,
  type Campaign,
  type CompetitorRelationship,
  type Contact,
  type Domain,
  type GEOObservation,
  type GuestPostOpportunity,
  type LinkGapOpportunity,
  type OpportunityScore,
  type OutreachStrategy,
} from "@/lib/types";
import Link from "next/link";

async function contactExtras(contact: Contact) {
  const [strategy, campaigns] = await Promise.all([
    apiGetOrNull<OutreachStrategy>(`/outreach/strategy/${contact.id}`),
    apiGet<Campaign[]>("/campaigns", { contact_id: contact.id }),
  ]);
  return { contact, strategy, campaigns };
}

export default async function DomainDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let domain: Domain;
  try {
    domain = await apiGet<Domain>(`/domains/${id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const [backlinksIn, competitors, linkGaps, contacts, guestPosts, score, geoObservations] =
    await Promise.all([
      apiGet<Backlink[]>("/backlinks", { target_domain_id: id }),
      apiGet<CompetitorRelationship[]>("/competitors", { primary_domain_id: id }),
      apiGet<LinkGapOpportunity[]>("/link-gaps", { primary_domain_id: id }),
      apiGet<Contact[]>("/contacts", { domain_id: id }),
      apiGet<GuestPostOpportunity[]>("/guest-posts", { domain_id: id }),
      apiPost<OpportunityScore>("/opportunities/score", undefined, { domain_id: id }),
      apiGet<GEOObservation[]>("/geo/observations", { target_domain_id: id }),
    ]);

  const contactRows = await Promise.all(contacts.map(contactExtras));
  const guestPost = guestPosts[0] ?? null;
  const startUrl = `https://${domain.normalized_host}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">{domain.normalized_host}</h1>
        <p className="text-sm text-slate-500">
          First seen {new Date(domain.first_seen_at).toLocaleString()} · Last crawled{" "}
          {domain.last_crawled_at ? new Date(domain.last_crawled_at).toLocaleString() : "never"}
        </p>
      </div>

      <Section title="Crawl">
        <form action={runCrawlAction} className="flex flex-wrap items-end gap-2">
          <input type="hidden" name="domain_id" value={id} />
          <div>
            <label className="block text-xs text-slate-500">URL</label>
            <input
              name="url"
              defaultValue={startUrl}
              required
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500">Max pages</label>
            <input
              name="max_pages"
              type="number"
              min={1}
              defaultValue={20}
              className="w-24 rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <SubmitButton pendingLabel="Crawling…">Run crawl</SubmitButton>
        </form>
      </Section>

      <Section title={`Backlinks to this domain (${backlinksIn.length})`}>
        {backlinksIn.length === 0 ? (
          <EmptyState>No verified backlinks to this domain yet.</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Anchor</th>
                <th>Type</th>
                <th>Rel</th>
                <th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {backlinksIn.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link href={`/backlinks/${b.id}`} className="text-slate-900 hover:underline">
                      {b.source_url}
                    </Link>
                  </td>
                  <td>{b.latest_observation.anchor_text || <span className="text-slate-400">—</span>}</td>
                  <td>
                    <Badge value={b.latest_observation.link_type} />
                  </td>
                  <td className="space-x-1">
                    {b.latest_observation.rel_nofollow && <Badge value="nofollow" />}
                    {b.latest_observation.rel_sponsored && <Badge value="sponsored" />}
                    {b.latest_observation.rel_ugc && <Badge value="ugc" />}
                  </td>
                  <td>{new Date(b.last_seen_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="Contacts">
        <form action={discoverContactsAction} className="mb-4 flex flex-wrap items-end gap-2">
          <input type="hidden" name="domain_id" value={id} />
          <div>
            <label className="block text-xs text-slate-500">Crawl start URL</label>
            <input
              name="start_url"
              defaultValue={startUrl}
              required
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <SubmitButton pendingLabel="Discovering…">Discover contacts</SubmitButton>
        </form>

        {contactRows.length === 0 ? (
          <EmptyState>No contacts discovered yet.</EmptyState>
        ) : (
          <div className="space-y-4">
            {contactRows.map(({ contact, strategy, campaigns }) => (
              <div key={contact.id} className="rounded border border-slate-200 p-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{contact.name ?? contact.email ?? contact.phone}</span>
                  {contact.job_title && <span className="text-slate-500">{contact.job_title}</span>}
                  {contact.email && <span className="text-slate-500">{contact.email}</span>}
                  <Badge value={contact.verification_status} />
                  {contact.email && (
                    <form action={verifyEmailAction}>
                      <input type="hidden" name="domain_id" value={id} />
                      <input type="hidden" name="contact_id" value={contact.id} />
                      <SubmitButton pendingLabel="Verifying…" variant="secondary">
                        Verify email
                      </SubmitButton>
                    </form>
                  )}
                </div>

                <div className="mt-3 border-t border-slate-100 pt-3">
                  {strategy ? (
                    <div className="space-y-2 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge value={strategy.opportunity_type} />
                        <Badge value={strategy.difficulty} />
                        {strategy.expected_link_probability !== null && (
                          <span className="text-slate-500">
                            {strategy.expected_link_probability}/100 expected link probability
                          </span>
                        )}
                      </div>
                      <p>{strategy.reason}</p>
                      {strategy.angle && (
                        <p className="italic text-slate-600">Angle: {strategy.angle}</p>
                      )}
                      <EvidenceList evidence={strategy.evidence} />

                      <form action={createCampaignAction} className="flex flex-wrap items-end gap-2 pt-2">
                        <input type="hidden" name="domain_id" value={id} />
                        <input type="hidden" name="outreach_strategy_id" value={strategy.id} />
                        <div>
                          <label className="block text-xs text-slate-500">Asset URL you&apos;re pitching</label>
                          <input
                            name="target_url"
                            required
                            placeholder="https://your-site.com/asset"
                            className="w-64 rounded border border-slate-300 px-3 py-1.5 text-sm"
                          />
                        </div>
                        <SubmitButton pendingLabel="Creating…" variant="secondary">
                          Start campaign
                        </SubmitButton>
                      </form>

                      {campaigns.length > 0 && (
                        <ul className="space-y-1 pt-2 text-sm">
                          {campaigns.map((c) => (
                            <li key={c.id}>
                              <Link href={`/campaigns/${c.id}`} className="hover:underline">
                                {c.target_url}
                              </Link>{" "}
                              <Badge value={c.current_stage} />
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ) : (
                    <form action={generateOutreachStrategyAction} className="flex flex-wrap items-end gap-2">
                      <input type="hidden" name="domain_id" value={id} />
                      <input type="hidden" name="contact_id" value={contact.id} />
                      <label className="flex items-center gap-1 text-xs text-slate-500">
                        <input type="checkbox" name="use_ai" defaultChecked />
                        AI-synthesized angle
                      </label>
                      <SubmitButton pendingLabel="Generating…" variant="secondary">
                        Generate outreach strategy
                      </SubmitButton>
                    </form>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Guest-post opportunity">
        <form action={discoverGuestPostAction} className="mb-4 flex flex-wrap items-end gap-2">
          <input type="hidden" name="domain_id" value={id} />
          <div>
            <label className="block text-xs text-slate-500">Crawl start URL</label>
            <input
              name="start_url"
              defaultValue={startUrl}
              required
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <SubmitButton pendingLabel="Checking…">Check for guest-post program</SubmitButton>
        </form>

        {guestPost ? (
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{guestPost.guest_post_probability}/100 probability</span>
              {guestPost.appears_closed && <Badge value="submissions closed" />}
            </div>
            {guestPost.guideline_page_url && (
              <p>
                Guidelines:{" "}
                <a href={guestPost.guideline_page_url} className="text-slate-700 underline">
                  {guestPost.guideline_page_url}
                </a>
              </p>
            )}
            {guestPost.editor_email && <p>Editor: {guestPost.editor_email}</p>}
            {(guestPost.word_count_min || guestPost.word_count_max) && (
              <p>
                Word count: {guestPost.word_count_min ?? "?"}–{guestPost.word_count_max ?? "?"}
              </p>
            )}
            <EvidenceList evidence={guestPost.evidence} />
          </div>
        ) : (
          <EmptyState>No guest-post program found yet.</EmptyState>
        )}
      </Section>

      <Section title="Opportunity score">
        <form action={computeOpportunityScoreAction} className="mb-4">
          <input type="hidden" name="domain_id" value={id} />
          <SubmitButton pendingLabel="Recomputing…" variant="secondary">
            Recompute
          </SubmitButton>
        </form>
        <div className="mb-3 text-2xl font-bold">
          {score.composite_score !== null ? score.composite_score : <span className="text-slate-400 text-base font-normal">not enough data</span>}
        </div>
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Value</th>
              <th>Confidence</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {score.components.map((c) => (
              <tr key={c.name}>
                <td>{c.name.replaceAll("_", " ")}</td>
                <td>{c.value ?? <span className="text-slate-400">—</span>}</td>
                <td>
                  <Badge value={c.confidence} />
                </td>
                <td className="text-slate-500">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Competitors & link gaps">
        <form action={addCompetitorAction} className="mb-4 flex flex-wrap items-end gap-2">
          <input type="hidden" name="primary_domain_id" value={id} />
          <div>
            <label className="block text-xs text-slate-500">Competitor host</label>
            <input
              name="competitor_host"
              required
              placeholder="competitor.com"
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <SubmitButton pendingLabel="Adding…" variant="secondary">
            Track competitor
          </SubmitButton>
        </form>

        {competitors.length === 0 ? (
          <EmptyState>No tracked competitors yet.</EmptyState>
        ) : (
          <p className="mb-3 text-sm text-slate-600">
            Tracking: {competitors.map((c) => c.competitor_host).join(", ")}
          </p>
        )}

        {linkGaps.length === 0 ? (
          <EmptyState>No link-gap opportunities found (need at least one tracked competitor with verified backlinks).</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Candidate domain</th>
                <th>Competitor overlap</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {linkGaps.map((g) => (
                <tr key={g.id}>
                  <td>{g.candidate_host}</td>
                  <td>{g.competitor_hosts.join(", ")}</td>
                  <td>
                    <Badge value={g.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="AI-search / GEO citations">
        <form action={recordGeoObservationAction} className="mb-4 grid gap-2 sm:grid-cols-2">
          <input type="hidden" name="domain_id" value={id} />
          <input
            name="query"
            required
            placeholder="Query you checked (e.g. best backlink tools)"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm sm:col-span-2"
          />
          <input
            name="engine"
            required
            placeholder="Engine (e.g. chatgpt_search, perplexity)"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <select
            name="observed_result"
            required
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            {GEO_CITATION_RESULTS.map((r) => (
              <option key={r} value={r}>
                {r.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <input
            name="source_url"
            placeholder="Cited URL (required if cited)"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm sm:col-span-2"
          />
          <div className="sm:col-span-2">
            <SubmitButton pendingLabel="Logging…" variant="secondary">
              Log observation
            </SubmitButton>
          </div>
        </form>

        {geoObservations.length === 0 ? (
          <EmptyState>
            No citation checks logged yet. No automated answer-engine integration exists (see
            docs/ARCHITECTURE.md risk #18) -- log what you see checking a real answer engine
            yourself.
          </EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Query</th>
                <th>Engine</th>
                <th>Result</th>
                <th>Source</th>
                <th>Observed</th>
              </tr>
            </thead>
            <tbody>
              {geoObservations.map((o) => (
                <tr key={o.id}>
                  <td>{o.query}</td>
                  <td>{o.engine}</td>
                  <td>
                    <Badge value={o.observed_result} />
                  </td>
                  <td>{o.source_url ?? <span className="text-slate-400">—</span>}</td>
                  <td>{new Date(o.observed_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}
