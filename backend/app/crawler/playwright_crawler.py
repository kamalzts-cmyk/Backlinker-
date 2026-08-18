"""Factory for the slow-path (JS-rendering) crawler. See docs/CRAWLER.md §1.

Only ever invoked for URLs the JS-detection heuristic escalated -- never
the default path. Concurrency is intentionally not shared with the HTTP
crawler's pool (docs/ARCHITECTURE.md risk #5): a handful of JS-heavy
pages must not starve the HTTP crawl queue.
"""

from collections.abc import Awaitable, Callable

from crawlee import ConcurrencySettings
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.storage_clients import MemoryStorageClient

from app.core.config import settings

_PLAYWRIGHT_CONCURRENCY = ConcurrencySettings(max_concurrency=2, desired_concurrency=2)


def build_playwright_crawler(
    *,
    max_pages: int,
    request_handler: Callable[[PlaywrightCrawlingContext], Awaitable[None]],
) -> PlaywrightCrawler:
    launch_options = {}
    if settings.playwright_executable_path:
        launch_options["executable_path"] = settings.playwright_executable_path
    if settings.playwright_no_sandbox:
        launch_options["args"] = ["--no-sandbox"]

    return PlaywrightCrawler(
        max_requests_per_crawl=max_pages,
        request_handler=request_handler,
        headless=True,
        concurrency_settings=_PLAYWRIGHT_CONCURRENCY,
        browser_launch_options=launch_options or None,
        storage_client=MemoryStorageClient(),
    )
