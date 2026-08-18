from app.crawler.extractors.links import LinkData
from app.db.models import BacklinkLinkType
from app.engines.backlink.classify import classify_link_type


def _link(**overrides) -> LinkData:
    defaults = {
        "target_url": "https://example.com/page",
        "anchor_text": "anchor",
        "surrounding_text": "context",
        "rel_nofollow": False,
        "rel_sponsored": False,
        "rel_ugc": False,
        "target_blank": False,
        "link_position": "body",
        "is_internal": False,
    }
    defaults.update(overrides)
    return LinkData(**defaults)


def test_sponsored_rel_wins_regardless_of_position():
    link = _link(rel_sponsored=True, link_position="nav")
    assert classify_link_type(link) == BacklinkLinkType.SPONSORED


def test_ugc_rel_classified():
    link = _link(rel_ugc=True)
    assert classify_link_type(link) == BacklinkLinkType.UGC


def test_nav_position_classified_navigation():
    link = _link(link_position="nav")
    assert classify_link_type(link) == BacklinkLinkType.NAVIGATION


def test_footer_position_classified_footer():
    link = _link(link_position="footer")
    assert classify_link_type(link) == BacklinkLinkType.FOOTER


def test_body_link_with_no_special_signal_is_unknown():
    # Deliberately UNKNOWN, not "editorial" -- classifying editorial
    # intent needs content judgment (Phase 12 AI), not guessed here.
    link = _link(link_position="body")
    assert classify_link_type(link) == BacklinkLinkType.UNKNOWN
