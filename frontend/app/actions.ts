"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { apiPost } from "@/lib/api";
import type { Campaign, Contact, Domain, GuestPostOpportunity, OutreachStrategy } from "@/lib/types";

function str(formData: FormData, key: string): string {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${key} is required`);
  }
  return value.trim();
}

function optionalStr(formData: FormData, key: string): string | undefined {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim() === "") return undefined;
  return value.trim();
}

function optionalInt(formData: FormData, key: string): number | undefined {
  const value = optionalStr(formData, key);
  return value === undefined ? undefined : Number.parseInt(value, 10);
}

export async function registerDomainAction(formData: FormData) {
  const domain = await apiPost<Domain>("/domains", { host: str(formData, "host") });
  redirect(`/domains/${domain.id}`);
}

export async function runCrawlAction(formData: FormData) {
  const job = await apiPost<{ id: string }>("/crawl", {
    url: str(formData, "url"),
    max_pages: optionalInt(formData, "max_pages"),
  });
  redirect(`/crawl/${job.id}`);
}

export async function addCompetitorAction(formData: FormData) {
  const primaryDomainId = str(formData, "primary_domain_id");
  await apiPost("/competitors", {
    primary_domain_id: primaryDomainId,
    competitor_host: str(formData, "competitor_host"),
  });
  revalidatePath(`/domains/${primaryDomainId}`);
}

export async function discoverContactsAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  await apiPost<Contact[]>("/contacts/discover", {
    start_url: str(formData, "start_url"),
    max_pages: optionalInt(formData, "max_pages"),
  });
  revalidatePath(`/domains/${domainId}`);
}

export async function verifyEmailAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  const contactId = str(formData, "contact_id");
  await apiPost(`/contacts/${contactId}/verify-email`);
  revalidatePath(`/domains/${domainId}`);
}

export async function discoverGuestPostAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  await apiPost<GuestPostOpportunity | null>("/guest-posts/discover", {
    start_url: str(formData, "start_url"),
    max_pages: optionalInt(formData, "max_pages"),
  });
  revalidatePath(`/domains/${domainId}`);
}

export async function computeOpportunityScoreAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  const referenceDomainId = optionalStr(formData, "reference_domain_id");
  await apiPost(
    "/opportunities/score",
    undefined,
    referenceDomainId
      ? { domain_id: domainId, reference_domain_id: referenceDomainId }
      : { domain_id: domainId }
  );
  revalidatePath(`/domains/${domainId}`);
}

export async function generateOutreachStrategyAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  const contactId = str(formData, "contact_id");
  const primaryDomainId = optionalStr(formData, "primary_domain_id");
  const useAi = formData.get("use_ai") === "on";
  await apiPost<OutreachStrategy>(
    "/outreach/strategy",
    undefined,
    primaryDomainId
      ? { contact_id: contactId, primary_domain_id: primaryDomainId, use_ai: useAi }
      : { contact_id: contactId, use_ai: useAi }
  );
  revalidatePath(`/domains/${domainId}`);
}

export async function createCampaignAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  await apiPost<Campaign>("/campaigns", {
    outreach_strategy_id: str(formData, "outreach_strategy_id"),
    target_url: str(formData, "target_url"),
  });
  revalidatePath(`/domains/${domainId}`);
}

export async function recordCampaignEventAction(formData: FormData) {
  const campaignId = str(formData, "campaign_id");
  await apiPost(`/campaigns/${campaignId}/events`, {
    stage: str(formData, "stage"),
    detail: optionalStr(formData, "detail"),
  });
  revalidatePath(`/campaigns/${campaignId}`);
}

export async function checkCampaignBacklinkAction(formData: FormData) {
  const campaignId = str(formData, "campaign_id");
  await apiPost(`/campaigns/${campaignId}/check-backlink`);
  revalidatePath(`/campaigns/${campaignId}`);
}

export async function recheckBacklinkAction(formData: FormData) {
  const backlinkId = str(formData, "backlink_id");
  await apiPost(`/backlinks/${backlinkId}/recheck`);
  revalidatePath(`/backlinks/${backlinkId}`);
}

export async function recordGeoObservationAction(formData: FormData) {
  const domainId = str(formData, "domain_id");
  await apiPost("/geo/observations", {
    query: str(formData, "query"),
    engine: str(formData, "engine"),
    target_domain_id: domainId,
    observed_result: str(formData, "observed_result"),
    source_url: optionalStr(formData, "source_url"),
    answer_excerpt: optionalStr(formData, "answer_excerpt"),
  });
  revalidatePath(`/domains/${domainId}`);
}
