"""
Scraper — Working
httpx + optional Playwright behind config flag. Default httpx.
Blocked-page check. List-item extraction.
"""
import asyncio
import csv
import json
import logging
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("scraper")

_CHALLENGE = ("cf-browser-verification", "cf-challenge", "just a moment", "attention required")


class FieldSpec(BaseModel):
    name: str
    selector: str
    attr: str | None = None


class ScrapeConfig(BaseModel):
    start_url: str
    item_selector: str | None = None
    fields: list[FieldSpec]
    next_page_selector: str | None = None
    max_pages: int = 5
    rate_limit_s: float = 1.2
    output: str = "out.csv"
    dry_run: bool = True
    resume_from: int = 0
    dedupe_on: str | None = None
    engine: str = "httpx"  # "httpx" | "playwright"


def blocked(status: int, body: str) -> bool:
    if status in (403, 429):
        return True
    head = (body or "")[:4000].lower()
    return any(marker in head for marker in _CHALLENGE)


def field_value(el, attr: str | None):
    if el is None:
        return None
    if not attr:
        return el.get_text(strip=True)
    val = el.get(attr)
    if isinstance(val, list):
        return " ".join(str(v) for v in val)
    return val


def next_url(soup: BeautifulSoup, current: str, selector: str | None) -> str | None:
    if not selector:
        return None
    nxt = soup.select_one(selector)
    href = nxt.get("href") if nxt is not None else None
    if not href:
        return None
    return urljoin(current, href)


def safe_output(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("output must be a relative path inside this folder")
    return path


class Scraper:
    def __init__(self, cfg: ScrapeConfig):
        self.cfg = cfg
        self.client = httpx.AsyncClient(
            headers={"User-Agent": "DelphiScraper/1.3"}, timeout=30, follow_redirects=True
        )
        self._pw = None
        self._browser = None

    async def _fetch_httpx(self, url: str) -> tuple[int, str]:
        r = await self.client.get(url)
        return r.status_code, r.text

    async def _fetch_playwright(self, url: str) -> tuple[int, str]:
        from playwright.async_api import async_playwright

        if self._pw is None:
            pw = await async_playwright().start()
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception:
                await pw.stop()
                raise
            self._pw = pw
            self._browser = browser
        page = await self._browser.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else 0
            html = await page.content()
            return status, html
        finally:
            await page.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, TimeoutError, OSError)),
        reraise=True,
    )
    async def fetch(self, url: str) -> tuple[int, str]:
        if self.cfg.engine == "playwright":
            return await self._fetch_playwright(url)
        return await self._fetch_httpx(url)

    def extract(self, soup: BeautifulSoup) -> list[dict]:
        containers = soup.select(self.cfg.item_selector) if self.cfg.item_selector else [soup]
        rows = []
        for c in containers:
            row = {f.name: field_value(c.select_one(f.selector), f.attr) for f in self.cfg.fields}
            if any(row.values()):
                rows.append(row)
        return rows

    async def run(self):
        res_rows, errors = [], []
        url, page, seen = self.cfg.start_url, 0, set()
        collected = 0
        while url and page < self.cfg.max_pages:
            try:
                status, html = await self.fetch(url)
                if blocked(status, html):
                    log.error("blocked %s status=%s len=%s — stop", url, status, len(html or ""))
                    errors.append(f"blocked:{url}")
                    break
                soup = BeautifulSoup(html, "lxml")
                if page < self.cfg.resume_from:
                    log.info("resume skip page %s", page)
                    url = next_url(soup, url, self.cfg.next_page_selector)
                    page += 1
                    if url and page < self.cfg.max_pages:
                        await asyncio.sleep(self.cfg.rate_limit_s)
                    continue
                rows = self.extract(soup)
                if not rows and collected == 0:
                    log.error("no elements matched on %s", url)
                    errors.append(f"no_match:{url}")
                collected += 1
                for row in rows:
                    key = row.get(self.cfg.dedupe_on) if self.cfg.dedupe_on else None
                    if key and key in seen:
                        continue
                    if key:
                        seen.add(key)
                    res_rows.append(row)
                log.info("page %s rows %s engine=%s", page, len(rows), self.cfg.engine)
                url = next_url(soup, url, self.cfg.next_page_selector)
            except Exception as e:
                errors.append(f"{url}: {e}")
                log.error("failed %s: %s", url, e)
                url = None
            page += 1
            if url and page < self.cfg.max_pages:
                await asyncio.sleep(self.cfg.rate_limit_s)
        if self.cfg.resume_from > 0 and collected == 0 and not any(str(e).startswith("blocked:") for e in errors):
            errors.append("resume_from not reached; set next_page_selector")
        if not self.cfg.dry_run and res_rows:
            self._write(res_rows)
        return res_rows, errors

    def _write(self, rows):
        path = safe_output(self.cfg.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        else:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    async def close(self):
        await self.client.aclose()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass


async def main(config_path: str = "config.json"):
    cfg = ScrapeConfig.model_validate_json(Path(config_path).read_text(encoding="utf-8"))
    s = Scraper(cfg)
    try:
        rows, errs = await s.run()
        print(f"rows={len(rows)} errors={len(errs)} dry_run={cfg.dry_run} engine={cfg.engine}")
        if errs:
            print("errors=" + json.dumps(errs))
        if cfg.dry_run:
            print(json.dumps(rows[:3], indent=2))
        if errs:
            raise SystemExit(1)
    finally:
        await s.close()


if __name__ == "__main__":
    asyncio.run(main())
