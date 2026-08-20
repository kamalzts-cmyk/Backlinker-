// Mirrors backend/app/api/schemas.py exactly -- no field here should
// exist that the API doesn't actually return, and no field the API
// returns should be missing. When the backend schema changes, this file
// changes with it; it isn't a separate contract.

export interface Domain {
  id: string;
  raw_host: string;
  normalized_host: string;
  first_seen_at: string;
  last_crawled_at: string | null;
}

export interface CrawlJobDetail {
  id: string;
  domain_id: string;
  start_url: string;
  status: string;
  max_pages: number;
  pages_crawled: number;
  started_at: string | null;
  finished_at: string | null;
  page_count: number;
  error_count: number;
}

export interface BacklinkObservation {
  id: string;
  anchor_text: string | null;
  surrounding_text: string | null;
  rel_nofollow: boolean;
  rel_sponsored: boolean;
  rel_ugc: boolean;
  link_position: string;
  link_type: string;
  source_type: string;
  confidence_score: number;
  observed_at: string;
}

export interface Backlink {
  id: string;
  source_url: string;
  target_url: string;
  first_seen_at: string;
  last_seen_at: string;
  latest_observation: BacklinkObservation;
}

export interface BacklinkDetail {
  id: string;
  source_url: string;
  target_url: string;
  first_seen_at: string;
  last_seen_at: string;
  observations: BacklinkObservation[];
}

export interface BacklinkMonitoringEvent {
  id: string;
  backlink_id: string;
  change_type: string;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  detail: string;
  detected_at: string;
}

export interface CompetitorRelationship {
  id: string;
  primary_domain_id: string;
  competitor_domain_id: string;
  competitor_host: string;
}

export interface LinkGapOpportunity {
  id: string;
  candidate_domain_id: string;
  candidate_host: string;
  competitor_overlap_count: number;
  competitor_hosts: string[];
  confidence: string;
  evidence: string[];
  computed_at: string;
}

export interface Contact {
  id: string;
  domain_id: string;
  name: string | null;
  job_title: string | null;
  email: string | null;
  phone: string | null;
  verification_status: string;
  confidence_score: number;
}

export interface GuestPostOpportunity {
  id: string;
  domain_id: string;
  guideline_page_url: string | null;
  editor_email: string | null;
  word_count_min: number | null;
  word_count_max: number | null;
  mentions_dofollow: boolean;
  mentions_nofollow: boolean;
  mentions_sponsored: boolean;
  mentions_author_bio: boolean;
  appears_closed: boolean;
  distinct_authors_observed: number;
  guest_post_probability: number;
  evidence: string[];
  computed_at: string;
}

export interface ScoreComponent {
  name: string;
  value: number | null;
  weight: number;
  confidence: string;
  detail: string;
}

export interface OpportunityScore {
  id: string;
  domain_id: string;
  reference_domain_id: string | null;
  composite_score: number | null;
  components: ScoreComponent[];
  evidence: string[];
  computed_at: string;
}

export interface OutreachStrategy {
  id: string;
  domain_id: string;
  contact_id: string;
  opportunity_type: string;
  guest_post_opportunity_id: string | null;
  link_gap_opportunity_id: string | null;
  reason: string;
  evidence: string[];
  angle: string | null;
  ai_generated: boolean;
  recommended_content_asset: string | null;
  expected_link_probability: number | null;
  difficulty: string;
  computed_at: string;
}

export interface CampaignEvent {
  id: string;
  stage: string;
  detail: string | null;
  occurred_at: string;
}

export interface Campaign {
  id: string;
  outreach_strategy_id: string;
  contact_id: string;
  target_url: string;
  current_stage: string | null;
  created_at: string;
}

export interface CampaignDetail extends Campaign {
  events: CampaignEvent[];
}

export interface GEOObservation {
  id: string;
  query: string;
  engine: string;
  target_domain_id: string;
  observed_result: string;
  source_url: string | null;
  answer_excerpt: string | null;
  observed_at: string;
}

export const CAMPAIGN_FUNNEL_STAGES = [
  "sent",
  "delivered",
  "bounced",
  "opened",
  "clicked",
  "replied",
  "positive_reply",
  "negative_reply",
  "unsubscribed",
  "published",
  "backlink_detected",
  "backlink_verified",
] as const;

export const REPORT_TYPES = [
  "backlinks",
  "link_gaps",
  "contacts",
  "guest_posts",
  "opportunity_scores",
] as const;

export const EXPORT_FORMATS = ["csv", "json", "xlsx", "pdf"] as const;

export const GEO_CITATION_RESULTS = ["cited", "not_cited"] as const;
