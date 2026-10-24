"""
Solana Agent GUI — Working
Paper auto-trade + clean local web GUI.
No private keys. No live signing. Each new signature appends an open paper row.

Run: python agent_gui.py
Open: http://127.0.0.1:8765
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
JUP_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def valid_pubkey(addr: str) -> bool:
    if not addr or len(addr) < 32 or len(addr) > 44:
        return False
    n = 0
    for ch in addr:
        i = _B58.find(ch)
        if i < 0:
            return False
        n = n * 58 + i
    pad = 0
    for ch in addr:
        if ch != "1":
            break
        pad += 1
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return len(b"\x00" * pad + full) == 32

PORT = int(os.getenv("GUI_PORT", "8765"))
RPCS = [r.strip() for r in os.getenv("SOLANA_RPCS", "https://api.mainnet-beta.solana.com").split(",") if r.strip()]
POLL_S = float(os.getenv("POLL_S", "20"))
STATE = Path("gui_state.json")

# In-memory + persisted
state = {
    "running": False,
    "dry_run": True,
    "watch": [],
    "positions": [],  # paper
    "log": [],
    "seen": {},
    "pnl": 0.0,
    "last_error": "",
}
lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def log(msg: str):
    with lock:
        state["log"].insert(0, {"ts": now(), "msg": msg})
        state["log"] = state["log"][:200]
    print(msg)


def save():
    with lock:
        now_ts = time.time()
        state["seen"] = {
            k: v for k, v in state["seen"].items()
            if isinstance(v, (int, float)) and now_ts - float(v) < 7 * 86400
        }
        if len(state["seen"]) > 2000:
            items = sorted(state["seen"].items(), key=lambda kv: float(kv[1]))
            state["seen"] = dict(items[-2000:])
        if len(state["positions"]) > 100:
            state["positions"] = state["positions"][-100:]
        STATE.write_text(json.dumps({
            "watch": state["watch"],
            "positions": state["positions"],
            "pnl": state["pnl"],
            "seen": state["seen"],
        }, indent=2), encoding="utf-8")


def load():
    if STATE.exists():
        try:
            d = json.loads(STATE.read_text())
            state["watch"] = d.get("watch", [])
            state["positions"] = d.get("positions", [])
            state["pnl"] = d.get("pnl", 0.0)
            state["seen"] = d.get("seen", {})
        except Exception:
            pass


class Engine:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20)
        self.idx = 0
        self._quote_at = 0.0
        self._quote_fail_at = 0.0
        self._quote_val = None

    async def rpc(self, method, params):
        last = None
        for _ in range(len(RPCS)):
            url = RPCS[self.idx % len(RPCS)]
            try:
                r = await self.client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                r.raise_for_status()
                j = r.json()
                if j.get("error"):
                    raise RuntimeError(str(j["error"]))
                return j
            except Exception as e:
                last = e
                self.idx += 1
        raise last or RuntimeError("rpc")

    async def paper_quote(self):
        now_ts = time.time()
        if self._quote_val is not None and now_ts - self._quote_at < 60:
            return self._quote_val
        if now_ts - self._quote_fail_at < 5:
            return self._quote_val
        val = None
        try:
            r = await self.client.get(
                JUP_QUOTE,
                params={
                    "inputMint": SOL_MINT,
                    "outputMint": USDC_MINT,
                    "amount": 50_000_000,
                    "slippageBps": 100,
                },
                timeout=10,
            )
            if r.status_code == 200:
                val = r.json().get("outAmount")
        except Exception:
            val = None
        if val is not None:
            self._quote_at = now_ts
            self._quote_val = val
        else:
            self._quote_fail_at = now_ts
        return val if val is not None else self._quote_val

    async def step(self) -> bool:
        with lock:
            if not state["running"] or not state["watch"]:
                return False
            addrs = list(state["watch"])
        changed = False
        quote = None
        for addr in addrs:
            try:
                data = await self.rpc("getSignaturesForAddress", [addr, {"limit": 5}])
            except Exception as e:
                with lock:
                    state["last_error"] = str(e)
                continue
            for item in data.get("result") or []:
                sig = item["signature"]
                key = f"{addr}|{sig}"
                with lock:
                    if key in state["seen"]:
                        continue
                if quote is None:
                    quote = await self.paper_quote()
                with lock:
                    state["seen"][key] = time.time()
                    state["positions"].append({
                        "id": sig,
                        "addr": addr,
                        "side": "paper_long",
                        "size_sol": 0.05,
                        "opened": now(),
                        "quote": quote,
                        "status": "open",
                    })
                log(f"PAPER OPEN {addr[:6]}… {sig[:8]} quote={quote}")
                changed = True
        return changed

    async def loop(self):
        while True:
            if Path("KILL").exists():
                with lock:
                    was = state["running"]
                    state["running"] = False
                if was:
                    log("KILL set — stopped")
            try:
                if await self.step():
                    save()
            except Exception as e:
                log(f"loop {e}")
            await asyncio.sleep(POLL_S)


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Delphi Solana Agent — Working</title>
<style>
  :root { --bg:#0f1115; --card:#1a1d24; --text:#e8eaed; --muted:#9aa0a6; --accent:#7cb8ff; --ok:#3ddc97; --warn:#f5a623; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:var(--bg); color:var(--text); }
  header { padding:16px 24px; border-bottom:1px solid #2a2e36; display:flex; justify-content:space-between; align-items:center; }
  h1 { font-size:18px; margin:0; font-weight:600; }
  .badge { font-size:12px; padding:4px 8px; border-radius:999px; background:#243044; color:var(--accent); }
  main { display:grid; grid-template-columns: 320px 1fr; gap:16px; padding:16px; }
  .card { background:var(--card); border-radius:12px; padding:16px; border:1px solid #2a2e36; }
  label { display:block; font-size:12px; color:var(--muted); margin-bottom:6px; }
  input, button { font:inherit; }
  input[type=text] { width:100%; padding:8px 10px; border-radius:8px; border:1px solid #333; background:#12141a; color:var(--text); }
  button { padding:8px 14px; border-radius:8px; border:0; cursor:pointer; font-weight:600; }
  .primary { background:var(--accent); color:#0b1220; }
  .ghost { background:#2a2e36; color:var(--text); }
  .danger { background:#3a2020; color:#ff8a80; }
  .row { display:flex; gap:8px; margin-top:8px; }
  ul { list-style:none; padding:0; margin:8px 0 0; }
  li { padding:8px 0; border-bottom:1px solid #2a2e36; font-size:13px; }
  .muted { color:var(--muted); font-size:12px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:8px; border-bottom:1px solid #2a2e36; }
  .ok { color:var(--ok); }
</style>
</head>
<body>
<header>
  <h1>Delphi Solana Agent <span class="badge">Working · Paper</span></h1>
  <div id="status" class="muted">stopped</div>
</header>
<main>
  <section class="card">
    <label>Watch address (public)</label>
    <input id="addr" type="text" placeholder="So111..."/>
    <div class="row">
      <button class="primary" onclick="add()">Add</button>
      <button class="ghost" onclick="toggle()">Start / Stop</button>
    </div>
    <p class="muted">Paper only. No key. New activity opens a 0.05 SOL simulated long.</p>
    <ul id="watch"></ul>
    <div class="row">
      <button class="danger" onclick="kill()">Kill switch</button>
    </div>
  </section>
  <section>
    <div class="card">
      <strong>Paper positions</strong>
      <table id="pos"><thead><tr><th>Addr</th><th>Side</th><th>Size</th><th>Opened</th></tr></thead><tbody></tbody></table>
    </div>
    <div class="card" style="margin-top:16px">
      <strong>Log</strong>
      <ul id="log"></ul>
    </div>
  </section>
</main>
<script>
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function refresh() {
  try {
  const r = await fetch('/api/state');
  const s = await r.json();
  document.getElementById('status').textContent = s.running ? 'running · paper' : 'stopped';
  document.getElementById('watch').innerHTML = s.watch.map(a => `<li>${esc(a.slice(0,6))}…${esc(a.slice(-4))}</li>`).join('') || '<li class="muted">none</li>';
  document.querySelector('#pos tbody').innerHTML = s.positions.slice(0,20).map(p => `<tr><td>${esc(String(p.addr||'').slice(0,6))}…</td><td class="ok">${esc(p.side)}</td><td>${esc(p.size_sol)}</td><td>${esc(String(p.opened||'').slice(11,19))}</td></tr>`).join('');
  document.getElementById('log').innerHTML = s.log.slice(0,15).map(l => `<li><span class="muted">${esc(String(l.ts||'').slice(11,19))}</span> ${esc(l.msg)}</li>`).join('');
  } catch (e) {}
}
async function add() {
  const addr = document.getElementById('addr').value.trim();
  if (!addr) return;
  await fetch('/api/watch', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({addr})});
  document.getElementById('addr').value = '';
  refresh();
}
async function toggle() { await fetch('/api/toggle', {method:'POST'}); refresh(); }
async function kill() { await fetch('/api/kill', {method:'POST'}); refresh(); }
setInterval(() => { if (!document.hidden) refresh(); }, 2000);
refresh();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            b = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path == "/api/state":
            with lock:
                self._json(200, state)
            return
        self._json(404, {"error": "not found"})

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            return None
        if n < 0 or n > 65536:
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def do_POST(self):
        data = self._body()
        if data is None:
            self._json(400, {"error": "json object required"})
            return
        if self.path == "/api/watch":
            addr = (data.get("addr") or "").strip()
            if not valid_pubkey(addr):
                self._json(400, {"error": "invalid public address"})
                return
            with lock:
                if addr not in state["watch"]:
                    state["watch"].append(addr)
            save()
            log(f"watch {addr[:6]}…")
            self._json(200, {"ok": True})
            return
        if self.path == "/api/toggle":
            if Path("KILL").exists() and not state["running"]:
                self._json(409, {"error": "KILL file is set. Delete KILL to start."})
                return
            with lock:
                state["running"] = not state["running"]
            log("started" if state["running"] else "stopped")
            self._json(200, {"running": state["running"]})
            return
        if self.path == "/api/kill":
            Path("KILL").write_text("1")
            with lock:
                state["running"] = False
            log("KILL set")
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        return


class LocalServer(ThreadingHTTPServer):
    # HTTPServer sets SO_REUSEADDR. On macOS that binds 127.0.0.1 beside a
    # wildcard listener, so a taken port looks free and this process never exits.
    allow_reuse_address = False

    def server_bind(self):
        # Skip HTTPServer.server_bind: it calls getfqdn(), which can stall on DNS.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def bind_server():
    try:
        return LocalServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(
            f"cannot bind 127.0.0.1:{PORT}: {e}. Set GUI_PORT to a free port.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


async def amain():
    load()
    eng = Engine()
    log(f"GUI http://127.0.0.1:{PORT}  (paper only)")
    try:
        await eng.loop()
    finally:
        await eng.client.aclose()


if __name__ == "__main__":
    httpd = bind_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        asyncio.run(amain())
    finally:
        httpd.shutdown()
        httpd.server_close()
