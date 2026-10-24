# Solana Agent — Working

Alert + optional paper Jupiter quote. Public addresses only. No private key. No signing.

## Why buyers pick this over a typical tracker script
- Dry-run prints the exact alert before Telegram is enabled
- Kill switch (`touch KILL` or `KILL_SWITCH=1`)
- Seen signatures saved and expired after 7 days (no duplicate spam on restart)
- RPC list with automatic fallback
- When MIN_SOL or a mint allowlist is set, a passing alert includes that note
- Coordinated flag when one signature hits multiple watched wallets
- Refuses to start if `LIVE=1` (this tier never signs)
- JSON log + console

## Run
```bash
cp .env.example .env
# fill WATCH_ADDRESSES (and Telegram if you want sends)
pip install -r requirements.txt
python agent.py
```
Set `DRY_RUN=0` only after the print looks right.

## What you do not get here
Live signing, private-key handling, or a custody wallet. Those stay out of this package on purpose.
