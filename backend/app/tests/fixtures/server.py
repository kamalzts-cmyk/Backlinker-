"""A tiny local HTTP server serving the fixture pages, plus a few
programmatic routes (redirect, 404, robots.txt) that a static file server
can't express. Used so crawler/extractor tests exercise real HTTP
requests/responses instead of parsing files off disk directly.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "html"

_ROBOTS_TXT = "User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"

_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base_url}/index.html</loc></url>
  <url><loc>{base_url}/author.html</loc></url>
</urlset>
"""


class _FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass  # keep test output clean

    def do_GET(self) -> None:
        base_url = f"http://{self.headers.get('Host', 'localhost')}"

        if self.path == "/robots.txt":
            self._respond(200, "text/plain", _ROBOTS_TXT.format(base_url=base_url).encode())
            return

        if self.path == "/sitemap.xml":
            self._respond(200, "application/xml", _SITEMAP_XML.format(base_url=base_url).encode())
            return

        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/index.html")
            self.end_headers()
            return

        if self.path == "/does-not-exist.html":
            self._respond(404, "text/html", b"<html><body>Not found</body></html>")
            return

        file_path = FIXTURES_DIR / self.path.lstrip("/")
        if self.path == "/":
            file_path = FIXTURES_DIR / "index.html"

        if file_path.is_file() and file_path.suffix == ".html":
            self._respond(200, "text/html", file_path.read_bytes())
        else:
            self._respond(404, "text/html", b"<html><body>Not found</body></html>")

    def _respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FixtureServer:
    """Context manager: `with FixtureServer() as base_url: ...`"""

    def __init__(self) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self._thread.start()
        port = self._httpd.server_address[1]
        return f"http://127.0.0.1:{port}"

    def __exit__(self, *exc_info) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
