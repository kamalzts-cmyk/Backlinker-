from app.crawler.normalize import normalize_host, normalize_url, registrable_domain_for_url


def test_normalize_host_strips_www_and_lowercases():
    assert normalize_host("WWW.Example.COM") == "example.com"


def test_normalize_host_strips_trailing_dot():
    assert normalize_host("example.com.") == "example.com"


def test_normalize_url_dedupes_www_scheme_and_trailing_slash():
    variants = [
        "https://www.example.com/page/",
        "http://example.com/page",
        "HTTPS://EXAMPLE.COM/page/",
    ]
    normalized = {normalize_url(v) for v in variants}
    # scheme is preserved (not merged across http/https) but host/path form matches
    assert all(n.endswith("example.com/page") for n in normalized)


def test_normalize_url_keeps_root_slash():
    assert normalize_url("https://example.com").endswith("example.com/")
    assert normalize_url("https://example.com/").endswith("example.com/")


def test_normalize_url_strips_default_port():
    assert normalize_url("https://example.com:443/page") == "https://example.com/page"
    assert "8443" in normalize_url("https://example.com:8443/page")


def test_normalize_url_drops_fragment_keeps_query():
    result = normalize_url("https://example.com/page?utm=1#section")
    assert "#" not in result
    assert "utm=1" in result


def test_registrable_domain_for_url():
    assert registrable_domain_for_url("https://www.example.com/post") == "example.com"
    # Only a *leading* "www." is stripped -- "blog.example.com" is a
    # distinct subdomain, not normalized away. Full public-suffix-list
    # registrable-domain resolution is a documented follow-up (see
    # normalize.py docstring and ARCHITECTURE.md risk #8).
    assert registrable_domain_for_url("https://blog.example.com/post") == "blog.example.com"
