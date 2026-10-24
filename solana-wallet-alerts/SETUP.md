# Setup — solana_alert / working

Working alert. Remembers signatures for 7 days, stops on a KILL file, and filters with MIN_SOL and MINT_ALLOWLIST when you set them. No key.

1. pip install -r requirements.txt
2. cp .env.example .env and set WATCH_ADDRESSES
3. python alert.py
