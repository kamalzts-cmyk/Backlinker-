"""Phase 16: backlink monitoring. See PRODUCT_SPEC.md §4.9:

    Verified backlinks are periodically re-crawled. Detect and alert on:
    new, lost, attribute changed (follow->nofollow, sponsored added),
    target/anchor changed, source page 404/redirected/deindexed,
    canonical changed. Alerts show explicit before/after state, not
    just "something changed."

Re-checking a backlink is exactly re-running Phase 3's candidate
verification for the same (source_url, target_url) pair -- no new crawl
mechanism, same precedent as every later engine reusing the Phase 1/2
crawler. `recheck_backlink` creates a fresh `BacklinkCandidate` for that
pair, verifies it for real, and diffs the new observation against the
backlink's previous `latest_observation` to produce explicit,
before/after `BacklinkMonitoringEvent` rows -- never a bare "something
changed."

Like `verify_candidate` (which this function calls), `recheck_backlink`
takes only IDs and manages its own `session_scope()` blocks rather than
a passed-in `Session` -- `verify_candidate` awaits a real crawl between
reading and writing, so the surrounding transaction must be committed
and reopened around it, not held open across the await. Callers (the API
layer, monitoring schedulers) fetch results via a fresh session
afterward.

"Target changed" from the spec's list isn't detected here: re-verifying
a candidate checks whether *this exact* target_url is still linked from
the source page, so a source page that now links somewhere else entirely
shows up as LOST (the original link is gone), not as a distinguishable
"retargeted" event -- this project doesn't have crawl data linking the
old and new target as the same logical mention, so it isn't guessed.
"""

import uuid
from datetime import UTC, datetime

from app.db.base import session_scope
from app.db.models import (
    Backlink,
    BacklinkChangeType,
    BacklinkMonitoringEvent,
    BacklinkObservation,
    BacklinkSourceType,
)
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate


def _snapshot(observation: BacklinkObservation) -> dict:
    return {
        "anchor_text": observation.anchor_text,
        "rel_nofollow": observation.rel_nofollow,
        "rel_sponsored": observation.rel_sponsored,
        "rel_ugc": observation.rel_ugc,
        "source_http_status": observation.source_http_status,
        "source_canonical_url": observation.source_canonical_url,
    }


async def recheck_backlink(backlink_id: uuid.UUID) -> list[dict]:
    """Returns the list of change-event dicts recorded (empty if
    nothing changed). Callers that want the ORM rows can query
    BacklinkMonitoringEvent by backlink_id afterward.
    """
    with session_scope() as session:
        backlink = session.get(Backlink, backlink_id)
        if backlink is None:
            raise ValueError(f"no such backlink: {backlink_id}")
        previous_observation = session.get(BacklinkObservation, backlink.latest_observation_id)
        previous = _snapshot(previous_observation) if previous_observation is not None else None
        source_url, target_url, target_domain_id = (
            backlink.source_url,
            backlink.target_url,
            backlink.target_domain_id,
        )
        last_seen_at = backlink.last_seen_at

    with session_scope() as session:
        candidate = create_candidate(
            session,
            source_url=source_url,
            target_url=target_url,
            target_domain_id=target_domain_id,
            source_type=BacklinkSourceType.DIRECT_CRAWL,
            discovery_method="monitoring_recheck",
        )
        candidate_id = candidate.id

    observation = await verify_candidate(candidate_id)

    events: list[dict] = []
    now = datetime.now(UTC)

    with session_scope() as session:
        backlink = session.get(Backlink, backlink_id)

        if observation is None:
            events.append(
                _record(
                    session,
                    backlink_id=backlink_id,
                    change_type=BacklinkChangeType.LOST,
                    before_state=previous,
                    after_state=None,
                    detail=(
                        f"Link no longer found at {source_url} "
                        f"(was present as of {last_seen_at.isoformat()})"
                    ),
                )
            )
            backlink.lost_at = now
            session.flush()
            return events

        if backlink.lost_at is not None:
            backlink.lost_at = None
            session.flush()

        if previous is None:
            return events

        new = _snapshot(observation)

        if (
            previous["rel_nofollow"] != new["rel_nofollow"]
            or previous["rel_sponsored"] != new["rel_sponsored"]
            or previous["rel_ugc"] != new["rel_ugc"]
        ):
            events.append(
                _record(
                    session,
                    backlink_id=backlink_id,
                    change_type=BacklinkChangeType.ATTRIBUTE_CHANGED,
                    before_state={
                        k: previous[k] for k in ("rel_nofollow", "rel_sponsored", "rel_ugc")
                    },
                    after_state={k: new[k] for k in ("rel_nofollow", "rel_sponsored", "rel_ugc")},
                    detail=(
                        f"Link attributes changed: nofollow {previous['rel_nofollow']}->"
                        f"{new['rel_nofollow']}, sponsored {previous['rel_sponsored']}->"
                        f"{new['rel_sponsored']}, ugc {previous['rel_ugc']}->{new['rel_ugc']}"
                    ),
                )
            )

        if previous["anchor_text"] != new["anchor_text"]:
            events.append(
                _record(
                    session,
                    backlink_id=backlink_id,
                    change_type=BacklinkChangeType.ANCHOR_CHANGED,
                    before_state={"anchor_text": previous["anchor_text"]},
                    after_state={"anchor_text": new["anchor_text"]},
                    detail=f"Anchor text changed: {previous['anchor_text']!r} -> {new['anchor_text']!r}",
                )
            )

        if previous["source_http_status"] != new["source_http_status"]:
            events.append(
                _record(
                    session,
                    backlink_id=backlink_id,
                    change_type=BacklinkChangeType.SOURCE_STATUS_CHANGED,
                    before_state={"source_http_status": previous["source_http_status"]},
                    after_state={"source_http_status": new["source_http_status"]},
                    detail=(
                        f"Source page HTTP status changed: {previous['source_http_status']} -> "
                        f"{new['source_http_status']}"
                    ),
                )
            )

        if previous["source_canonical_url"] != new["source_canonical_url"]:
            events.append(
                _record(
                    session,
                    backlink_id=backlink_id,
                    change_type=BacklinkChangeType.CANONICAL_CHANGED,
                    before_state={"source_canonical_url": previous["source_canonical_url"]},
                    after_state={"source_canonical_url": new["source_canonical_url"]},
                    detail=(
                        f"Source canonical URL changed: {previous['source_canonical_url']} -> "
                        f"{new['source_canonical_url']}"
                    ),
                )
            )

        return events


def _record(
    session,
    *,
    backlink_id: uuid.UUID,
    change_type: BacklinkChangeType,
    before_state: dict | None,
    after_state: dict | None,
    detail: str,
) -> dict:
    event = BacklinkMonitoringEvent(
        backlink_id=backlink_id,
        change_type=change_type,
        before_state=before_state,
        after_state=after_state,
        detail=detail,
    )
    session.add(event)
    session.flush()
    return {
        "id": event.id,
        "change_type": change_type,
        "before_state": before_state,
        "after_state": after_state,
        "detail": detail,
    }
