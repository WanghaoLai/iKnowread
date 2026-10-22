"""Release-check-only origin used to exercise Crawl4AI redirect handling."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ARTICLE_TEXT = " ".join(
    f"Safe public crawl marker section {index} contains enough ordinary article text for extraction."
    for index in range(1, 41)
)
ARTICLE = (
    "<!doctype html><html><head><title>docker-ssrf-public-article</title></head>"
    f"<body><main><h1>Public article</h1><p>{ARTICLE_TEXT}</p></main></body></html>"
).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/redirect-internal":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:11235/health")
            self.end_headers()
            return
        if self.path in {"/health", "/article"}:
            content = b"ok" if self.path == "/health" else ARTICLE
            self.send_response(200)
            self.send_header("Content-Type", "text/plain" if self.path == "/health" else "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(404)

    def log_message(self, _format: str, *_args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
