"""
Automation — Working
Webhook in, echo out, failure row written, GET /health.
If the port is busy, set PORT to a free port.
"""
import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = os.getenv("OUT_SHEET", "runs.jsonl")
MAX_BODY = 1_000_000


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send(200, {"ok": True})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def _read(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            return None, 400, "bad content-length"
        if n < 0 or n > MAX_BODY:
            return None, 413, "body too large"
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return None, 400, "invalid json"
        if not isinstance(data, dict):
            return None, 400, "json object required"
        return data, 200, ""

    def do_POST(self):
        data, code, err = self._read()
        if data is None:
            self._send(code, {"ok": False, "error": err})
            return
        try:
            result = {"ok": True, "echo": str(data.get("text", ""))[:200]}
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
            self._send(200, result)
        except Exception as e:
            err_row = {"ok": False, "error": str(e)}
            try:
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(err_row) + "\n")
            except Exception:
                pass
            self._send(500, err_row)

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, fmt, *args):
        return


class LocalServer(HTTPServer):
    # Stock HTTPServer sets SO_REUSEADDR. On macOS that binds beside a wildcard
    # listener, so a taken port looks free. Also skip getfqdn(), which can stall.
    allow_reuse_address = False

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8787"))
    print(f"listening :{port} → {OUT}")
    try:
        LocalServer(("127.0.0.1", port), H).serve_forever()
    except OSError as e:
        print(f"cannot bind 127.0.0.1:{port}: {e}. Set PORT to a free port.", file=sys.stderr)
        sys.exit(1)
