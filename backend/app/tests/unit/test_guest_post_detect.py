from app.engines.guest_post.detect import _extract_word_count_range, _mentions_any


def test_extract_word_count_range():
    assert _extract_word_count_range("Articles should be 1200-2000 words") == (1200, 2000)
    assert _extract_word_count_range("aim for 800 to 1200 words please") == (800, 1200)


def test_extract_word_count_range_none_when_absent():
    assert _extract_word_count_range("no length requirement mentioned") == (None, None)


def test_mentions_any_case_insensitive():
    assert _mentions_any("We love DoFollow links", "dofollow") is True
    assert _mentions_any("nothing relevant here", "dofollow") is False
