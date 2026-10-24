"""
Solana Agent — Working
Alert + paper quote. No private keys. No signing.

Why this beats the usual Telegram tracker script:
- Dry-run default (prints before any Telegram send)
- Kill switch: touch KILL or set KILL_SWITCH=1
- Seen signatures persisted with timestamps; entries older than 7 days drop
- RPC fallback list (rotates on failure)
- When MIN_SOL or a mint allowlist is set, the gate runs; a passing alert then includes that note
- Optional paper Jupiter quote (public endpoint, no wallet)
- Structured JSON log (agent.log) plus console
- Coordinated flag when the same signature hits more than one watched address
- Refuses to start if LIVE=1 (this tier never signs)

Config is environment variables. See .env.example.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOG_PATH = Path("agent.log")
SEEN_PATH = Path("seen.json")
KILL_PATH = Path("KILL")
EXPIRE_S = 7 * 24 * 3600

RPCS = [r.strip() for r in os.getenv("SOLANA_RPCS", "https://api.mainnet-beta.solana.com").split(",") if r.strip()]
WATCH = [a.strip() for a in os.getenv("WATCH_ADDRESSES", "").split(",") if a.strip()]
MIN_SOL = float(os.getenv("MIN_SOL", "0"))
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
PAPER = os.getenv("PAPER_QUOTE", "1") == "1"
DRY = os.getenv("DRY_RUN", "1") == "1"
LIVE = os.getenv("LIVE", "0") == "1"
POLL_S = float(os.getenv("POLL_S", "20"))
QUOTE_MINT = os.getenv("QUOTE_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")  # USDC
JUP_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
QUOTE_TTL = 60
WINDOW_S = 3600
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


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


ALLOW = {m.strip() for m in os.getenv("MINT_ALLOWLIST", "").split(",") if valid_pubkey(m.strip())}


def short_addr(addr: str) -> str:
    if len(addr) <= 12:
        return addr
    return f"{addr[:6]}…{addr[-4:]}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("sol_agent_working")


def killed() -> bool:
    return KILL_PATH.exists() or os.getenv("KILL_SWITCH", "0") == "1"


def refuse_live() -> None:
    if LIVE:
        print("REFUSING TO START: LIVE=1 is set.", file=sys.stderr)
        print("Working tier never signs and never holds a key.", file=sys.stderr)
        print("Unset LIVE (or set LIVE=0) to run in alert/paper mode.", file=sys.stderr)
        sys.exit(2)


@dataclass
class Alert:
    addr: str
    sig: str
    slot: int | None
    coordinated: bool = False
    quote: str = ""
    extra: dict = field(default_factory=dict)

    def line(self) -> str:
        base = f"Activity {short_addr(self.addr)} sig={self.sig[:10]} slot={self.slot}"
        if self.coordinated:
            base += " COORDINATED"
        if self.quote:
            base += f" | {self.quote}"
        if ALLOW:
            base += " allowlist=pass"
        if MIN_SOL > 0:
            base += f" min_sol={MIN_SOL:g}"
        return base


class WorkingAgent:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=25)
        self.bot = None
        if TG_TOKEN:
            from telegram import Bot
            self.bot = Bot(TG_TOKEN)
        self.seen: dict[str, float] = {}
        self.rpc_idx = 0
        self.window: dict[str, tuple[float, list[str]]] = {}
        self.quote_cache: dict[str, tuple[float, str]] = {}
        self._load_seen()

    def _load_seen(self) -> None:
        if not SEEN_PATH.exists():
            return
        try:
            raw = json.loads(SEEN_PATH.read_text())
            now = time.time()
            if isinstance(raw, list):
                self.seen = {s: now for s in raw}
            else:
                self.seen = {k: float(v) for k, v in raw.items() if now - float(v) < EXPIRE_S}
        except Exception as e:
            log.warning("seen load failed: %s", e)
            self.seen = {}

    def _save_seen(self) -> None:
        now = time.time()
        self.seen = {k: v for k, v in self.seen.items() if now - v < EXPIRE_S}
        SEEN_PATH.write_text(json.dumps(self.seen))

    async def rpc(self, method: str, params: list) -> dict:
        last: Exception | None = None
        for _ in range(len(RPCS)):
            url = RPCS[self.rpc_idx % len(RPCS)]
            try:
                r = await self.client.post(
                    url,
                    json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                )
                r.raise_for_status()
                data = r.json()
                if data.get("error"):
                    raise RuntimeError(str(data["error"]))
                return data
            except Exception as e:
                last = e
                self.rpc_idx += 1
                log.warning("rpc fail %s: %s", url, e)
        raise last or RuntimeError("all rpcs failed")

    async def paper_quote(self, mint: str) -> str:
        now = time.time()
        hit = self.quote_cache.get(mint)
        if hit and now - hit[0] < hit[2]:
            return hit[1]
        text = "no quote"
        ok = False
        try:
            r = await self.client.get(
                JUP_QUOTE,
                params={
                    "inputMint": SOL_MINT,
                    "outputMint": mint,
                    "amount": 50_000_000,
                    "slippageBps": 100,
                },
                timeout=10,
            )
            if r.status_code == 200:
                j = r.json()
                amount = j.get("outAmount")
                if amount is not None:
                    text = f"paper out={amount} routes={len(j.get('routePlan', []))}"
                    ok = True
            else:
                text = f"quote status {r.status_code}"
        except Exception as e:
            text = f"quote err {e}"
        self.quote_cache[mint] = (now, text, QUOTE_TTL if ok else 5)
        return text

    async def gate(self, addr: str, sig: str) -> bool | None:
        """True alerts. False remembers and skips. None retries on a later poll."""
        if MIN_SOL <= 0 and not ALLOW:
            return True
        try:
            data = await self.rpc(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            )
        except Exception as e:
            log.warning("gate %s: %s", sig[:8], e)
            return None
        tx = data.get("result")
        if not tx:
            return None
        meta = tx.get("meta") or {}
        if MIN_SOL > 0:
            keys = ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
            owners = [key.get("pubkey") if isinstance(key, dict) else key for key in keys]
            if addr not in owners:
                return False
            i = owners.index(addr)
            pre = meta.get("preBalances") or []
            post = meta.get("postBalances") or []
            if i >= len(pre) or i >= len(post):
                return False
            if abs(int(pre[i]) - int(post[i])) / 1_000_000_000 < MIN_SOL:
                return False
        if ALLOW:
            blob = json.dumps(meta.get("preTokenBalances") or []) + json.dumps(meta.get("postTokenBalances") or [])
            if not any(mint in blob for mint in ALLOW):
                return False
        return True

    async def collect(self, addr: str) -> list[Alert]:
        data = await self.rpc("getSignaturesForAddress", [addr, {"limit": 8}])
        found = []
        local = set()
        skipped = False
        for item in data.get("result") or []:
            sig = item["signature"]
            key = f"{addr}|{sig}"
            # Key by address and signature. Marking the signature alone drops
            # every later watched address that appears in the same transaction.
            if key in self.seen or sig in local:
                continue
            decision = await self.gate(addr, sig)
            if decision is None:
                continue
            local.add(sig)
            if decision is False:
                self.seen[key] = time.time()
                skipped = True
                continue
            found.append(Alert(addr=addr, sig=sig, slot=item.get("slot")))
        if skipped:
            self._save_seen()
        return found

    async def emit(self, batch: list[Alert]) -> None:
        now = time.time()
        self.window = {sig: pair for sig, pair in self.window.items() if now - pair[0] < WINDOW_S}
        for alert in batch:
            ts, addrs = self.window.get(alert.sig, (now, []))
            if alert.addr not in addrs:
                addrs = [*addrs, alert.addr]
            self.window[alert.sig] = (now, addrs)
        quote = await self.paper_quote(QUOTE_MINT) if PAPER and batch else ""
        for alert in batch:
            alert.coordinated = len(self.window[alert.sig][1]) > 1
            alert.quote = quote
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "addr": alert.addr,
                "sig": alert.sig,
                "slot": alert.slot,
                "coordinated": alert.coordinated,
                "dry": DRY,
            }
            log.info(json.dumps(rec))
            line = alert.line()
            if self.bot and TG_CHAT and not DRY:
                try:
                    await self.bot.send_message(chat_id=TG_CHAT, text=line[:4000])
                except Exception as e:
                    log.error("telegram: %s", e)
            else:
                print("[DRY]" if DRY else "[LOCAL]", line)
        for alert in batch:
            self.seen[f"{alert.addr}|{alert.sig}"] = now
        self._save_seen()

    async def loop(self) -> None:
        if killed():
            log.warning("kill switch already set — exiting")
            return
        good = []
        for addr in WATCH:
            if valid_pubkey(addr):
                good.append(addr)
            else:
                log.error("skip invalid address len=%s", len(addr))
        if not good:
            log.error("WATCH_ADDRESSES is empty. Set at least one public address.")
            return
        log.info(
            "watching %s dry=%s paper=%s allow=%s min_sol=%s rpcs=%s (gate filters when MIN_SOL>0 or allowlist set; passing alerts include the note)",
            len(good), DRY, PAPER, len(ALLOW), MIN_SOL, len(RPCS),
        )
        while not killed():
            batch: list[Alert] = []
            for addr in good:
                if killed():
                    break
                try:
                    batch.extend(await self.collect(addr))
                except Exception as e:
                    log.error("poll %s: %s", short_addr(addr), e)
            if batch:
                await self.emit(batch)
            await asyncio.sleep(POLL_S)
        log.warning("kill switch triggered — clean exit")

    async def close(self) -> None:
        await self.client.aclose()


async def main() -> None:
    refuse_live()
    agent = WorkingAgent()
    try:
        await agent.loop()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
