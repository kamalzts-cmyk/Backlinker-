"""Deterministic link-type classification. See docs/DATABASE.md
§Backlink engine and app/db/models.py's BacklinkLinkType docstring for
why this is intentionally a small subset of the full taxonomy in
PRODUCT_SPEC.md §4.2 -- everything beyond structural/rel-attribute facts
requires content judgment and belongs to Phase 12 (AI link-context
classification), not this module.
"""

from app.crawler.extractors.links import LinkData
from app.db.models import BacklinkLinkType


def classify_link_type(link: LinkData) -> BacklinkLinkType:
    if link.rel_sponsored:
        return BacklinkLinkType.SPONSORED
    if link.rel_ugc:
        return BacklinkLinkType.UGC
    if link.link_position == "nav":
        return BacklinkLinkType.NAVIGATION
    if link.link_position == "footer":
        return BacklinkLinkType.FOOTER
    return BacklinkLinkType.UNKNOWN
