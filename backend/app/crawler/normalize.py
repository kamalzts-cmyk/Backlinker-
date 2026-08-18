"""The single source of truth for URL/domain normalization.

docs/ARCHITECTURE.md risk #8: every engine keys off a normalized domain,
so this must be centralized and reused everywhere -- never
re-implemented per engine.
"""

from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_host(host: str) -> str:
    """Lowercase, strip a leading www., IDNA-encode. Does not attempt full
    public-suffix-list registrable-domain resolution -- adequate for
    Phase 1's own-site crawling; revisit before Phase 5 (competitor
    domains may be presented with varying subdomains).
    """
    host = host.strip().lower().rstrip(".")
    host = host.removeprefix("www.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass  # already ASCII or invalid; leave as-is rather than raise
    return host


def normalize_url(url: str) -> str:
    """Canonicalize scheme/host/port/path for deduplication purposes.

    - lowercase scheme and host
    - strip default port
    - strip a trailing slash on the path (except root "/")
    - drop the fragment
    - keep the query string as-is (query params can be meaningful)
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "http"
    host = normalize_host(parts.hostname or "")
    port = parts.port
    netloc = host
    if port and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def registrable_domain_for_url(url: str) -> str:
    """normalized_host for a given URL -- the join key used everywhere."""
    return normalize_host(urlsplit(url).hostname or "")
