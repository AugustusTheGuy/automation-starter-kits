# Setup — solana_agent / working

Working agent. Paper quote, kill switch, 7-day seen file. When MIN_SOL or a mint allowlist is set, the gate runs; a passing alert then includes that note. No key.

1. pip install -r requirements.txt
2. cp .env.example .env and fill WATCH_ADDRESSES
3. python agent.py
4. Set DRY_RUN=0 only after the print looks right.
