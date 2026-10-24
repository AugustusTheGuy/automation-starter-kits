# automation-starter-kits

Small, self-contained Python tools for common freelance automation jobs. Each folder runs on its own with a `requirements.txt`, a `SETUP.md`, and safe defaults: dry-run first, kill switches, no private keys.

| Folder | What it does | Stack |
|---|---|---|
| [`web-scraper/`](web-scraper) | Config-driven scraper: CSS-selector fields, list items, next-page following, block/challenge-page detection, retries with backoff, CSV output. Optional Playwright engine for JavaScript sites. | httpx, BeautifulSoup/lxml, pydantic, tenacity, Playwright (optional) |
| [`webhook-relay/`](webhook-relay) | Minimal webhook receiver: `POST /` accepts JSON, appends a result row (or a failure row) to a JSON-lines log, `GET /health`. Body-size limit, JSON validation, clear error if the port is taken. | Python standard library |
| [`llm-agent-guarded/`](llm-agent-guarded) | Answers a question over local `.txt` docs through any OpenAI-compatible chat endpoint, with a human approval gate, step limit, cost cap and a JSON-lines trace. Runs as a dry run when no key is set. | httpx |
| [`solana-wallet-alerts/`](solana-wallet-alerts) | Watches public Solana addresses over RPC and sends Telegram alerts for new signatures. Base58 pubkey validation, `MIN_SOL` and mint-allowlist filters, 7-day seen-signature store, `KILL` file. | httpx, python-telegram-bot |
| [`solana-paper-watcher/`](solana-paper-watcher) | Alert agent with RPC fallback, optional paper quote from Jupiter's public quote API, coordinated-activity flag across watched wallets, structured JSON log. Refuses to start with `LIVE=1`. | httpx, asyncio |
| [`solana-paper-dashboard/`](solana-paper-dashboard) | Local web dashboard (`127.0.0.1:8765`) that records paper positions for new signatures on watched addresses. | Python `http.server`, httpx |

None of the Solana tools hold, ask for, or sign with a private key. They read public chain data only.

## Quick start

```bash
cd webhook-relay && python glue.py            # then: curl -XPOST localhost:8787 -d '{"text":"hi"}'
cd web-scraper && pip install -r requirements.txt && python scraper.py   # edit config.json first
cd solana-wallet-alerts && cp .env.example .env && pip install -r requirements.txt && python alert.py
```

See each folder's `SETUP.md` for setup steps.

## Tests

```bash
pip install httpx beautifulsoup4 lxml "pydantic>=2" tenacity python-telegram-bot
python -m unittest discover -s tests -v
```

Offline smoke tests: every script compiles; the webhook relay is started on a free port and checked for `/health`, a valid POST, a 400 on bad JSON and the log row; scraper challenge-page detection; Solana pubkey validation; and the paper watcher refusing `LIVE=1`.

## License

MIT
