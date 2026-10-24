# Solana Agent GUI — Working

Paper auto-trade + local web GUI. No private keys.

```bash
pip install -r requirements.txt
python agent_gui.py
# open http://127.0.0.1:8765
```

Add a public address, press Start. New on-chain activity opens a simulated 0.05 SOL long. Kill switch writes a KILL file and stops.

This is the Working tier: one watch list, paper only, activity log, start/stop.
