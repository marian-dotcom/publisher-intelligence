"""Controlled benchmark target for the local browser-worker benchmark.

Serves deterministic, bounded pages on the compose network so browser-worker
replicas exercise the REAL production checkpoint path against a safe target.
Never point production monitoring at this service.
"""

import http.server


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            b"<!doctype html><html><head><title>Bench</title></head>"
            b"<body><main><h1>benchmark target</h1><p>stable content</p></main></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8099), Handler)
    server.serve_forever()
