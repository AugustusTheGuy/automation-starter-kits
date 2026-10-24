"""
Solana Alert — Working
Paper/alert only. No private keys.
Seen signatures persist for 7 days. Kill via KILL file or KILL_SWITCH=1.
Single public RPC. Professional adds RPC failover.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx
from telegram import Bot

log = logging.getLogger("sol_alert_working")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
WATCH = [a.strip() for a in os.getenv("WATCH_ADDRESSES", "").split(",") if a.strip()]
DRY = os.getenv("DRY_RUN", "1") == "1"
MIN_SOL = float(os.getenv("MIN_SOL", "0"))
SEEN_FILE = Path("seen.json")
KILL_FILE = Path("KILL")
EXPIRE_S = 7 * 24 * 3600
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def killed() -> bool:
    return KILL_FILE.exists() or os.getenv("KILL_SWITCH", "0") == "1"


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


class AlertBot:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20)
        self.bot = Bot(TG_TOKEN) if TG_TOKEN else None
        self.seen: dict[str, float] = {}
        self._load()

    def _load(self):
        if not SEEN_FILE.exists():
            return
        try:
            raw = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            now = time.time()
            if isinstance(raw, list):
                self.seen = {s: now for s in raw}
            elif isinstance(raw, dict):
                self.seen = {k: float(v) for k, v in raw.items() if now - float(v) < EXPIRE_S}
        except Exception as e:
            log.warning("seen load failed: %s", e)
            self.seen = {}

    def _save(self):
        now = time.time()
        self.seen = {k: v for k, v in self.seen.items() if now - v < EXPIRE_S}
        SEEN_FILE.write_text(json.dumps(self.seen), encoding="utf-8")

    async def rpc(self, method: str, params: list) -> dict:
        r = await self.client.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data

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

    async def poll_address(self, addr: str) -> int:
        data = await self.rpc("getSignaturesForAddress", [addr, {"limit": 5}])
        now = time.time()
        new = 0
        for item in data.get("result") or []:
            sig = item["signature"]
            key = f"{addr}|{sig}"
            if key in self.seen:
                continue
            decision = await self.gate(addr, sig)
            if decision is None:
                continue
            if decision is False:
                self.seen[key] = now
                new += 1
                log.info("skip %s filter", sig[:8])
                continue
            msg = f"Activity on {short_addr(addr)} sig={sig[:8]}… slot={item.get('slot')}"
            if ALLOW:
                msg += " allowlist=pass"
            if MIN_SOL > 0:
                msg += f" min_sol={MIN_SOL:g}"
            log.info(msg)
            delivered = False
            if self.bot and TG_CHAT and not DRY:
                try:
                    await self.bot.send_message(chat_id=TG_CHAT, text=msg)
                    delivered = True
                except Exception as e:
                    log.error("telegram: %s", e)
            else:
                print("[DRY]" if DRY else "[LOCAL]", msg)
                delivered = True
            if delivered:
                self.seen[key] = now
                new += 1
        if new:
            self._save()
        return new

    async def loop(self):
        if killed():
            log.warning("kill switch already set — exiting")
            return
        good, bad = [], []
        for addr in WATCH:
            (good if valid_pubkey(addr) else bad).append(addr)
        for addr in bad:
            log.error("skip invalid address len=%s", len(addr))
        if not good:
            log.error("Set WATCH_ADDRESSES")
            return
        log.info("watching %s dry=%s (seen expires 7d)", len(good), DRY)
        while not killed():
            for addr in good:
                if killed():
                    break
                try:
                    await self.poll_address(addr)
                except Exception as e:
                    log.error("poll %s: %s", short_addr(addr), e)
            await asyncio.sleep(float(os.getenv("POLL_S", "15")))
        log.warning("kill switch triggered — clean exit")

    async def close(self):
        await self.client.aclose()


async def main():
    b = AlertBot()
    try:
        await b.loop()
    finally:
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
