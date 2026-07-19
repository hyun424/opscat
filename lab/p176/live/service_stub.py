from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in {"/health", "/metadata"}:
            self.send_error(404)
            return
        payload: dict[str, Any] = {
            "ok": True,
            "schema_version": "p176.live_local_service.v1",
            "service_id": os.environ["P176_SERVICE_ID"],
            "role": os.environ["P176_LIVE_ROLE"],
        }
        if self.path == "/metadata":
            payload["criticality_tier"] = os.environ.get("P176_CRITICALITY_TIER")
            payload["ownership_domain"] = os.environ.get("P176_OWNERSHIP_DOMAIN")
            payload["depends_on"] = [item for item in os.environ.get("P176_DEPENDS_ON", "").split(",") if item]
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> None:
    port = int(os.environ["P176_PORT"])
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
