"""Factory for the fast-path crawler. See docs/CRAWLER.md §1.

Thin wrapper around Crawlee's BeautifulSoupCrawler -- we use Crawlee's
frontier/retry/robots primitives (docs/ARCHITECTURE.md §5) rather than
reimplementing them; this module only fixes the project's defaults.
"""

import uuid
from collections.abc import Awaitable, Callable

from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
from crawlee.http_clients import HttpxHttpClient
from crawlee.storage_clients import MemoryStorageClient
from crawlee.storages import RequestQueue

from app.core.config import settings

FailedRequestHandler = Callable[..., Awaitable[None]]


async def build_http_crawler(
    *,
    max_pages: int,
    request_handler: Callable[[BeautifulSoupCrawlingContext], Awaitable[None]],
    failed_request_handler: FailedRequestHandler | None = None,
) -> BeautifulSoupCrawler:
    # A uniquely-*named* queue, not just a fresh MemoryStorageClient
    # instance: Crawlee resolves storages by name against a process-wide
    # registry, so two separate crawler runs that both use the implicit
    # "default" queue name can leak pending/discovered requests into each
    # other even with a brand-new storage_client object (confirmed while
    # building Phase 5 -- verifying two candidates that share the same
    # source_url caused the second run to pick up the first run's
    # same-domain-filtered-out external links and try to fetch them).
    storage_client = MemoryStorageClient()
    request_queue = await RequestQueue.open(
        name=f"http-crawl-{uuid.uuid4()}", storage_client=storage_client
    )

    crawler = BeautifulSoupCrawler(
        max_requests_per_crawl=max_pages,
        respect_robots_txt_file=settings.crawler_respect_robots_txt,
        request_handler=request_handler,
        # Let the handler see error responses (e.g. a broken-link check)
        # instead of Crawlee treating every non-2xx/3xx as a hard failure.
        ignore_http_error_status_codes=list(range(400, 600)),
        request_manager=request_queue,
        storage_client=storage_client,
        # Crawlee's default HTTP client (impit) does not reliably honor
        # HTTPS_PROXY-style environment proxy config on every platform;
        # httpx does, and any real deployment sitting behind an egress
        # proxy needs that. See docs/CRAWLER.md.
        http_client=HttpxHttpClient(),
    )
    if failed_request_handler is not None:
        crawler.failed_request_handler(failed_request_handler)
    return crawler
