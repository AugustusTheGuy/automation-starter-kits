# solana-wallet-alerts-rs

Read-only Rust port of `solana-wallet-alerts/alert.py`, including `--registry`. It holds no key and signs nothing. There is no second devnet deploy.

## Usage

This is an RPC client, not an RPC node. A node would need a full ledger and would not add résumé evidence beyond this client.

One compile downloaded crates onto NoxSSD and finished `cargo test` in 28.45s. Internal disk stayed at 4 GB free. Runtime SOL cost is 0. Each pass calls `getSignaturesForAddress` with limit 5 for every watch. `getTransaction` is called only when `MIN_SOL` or `MINT_ALLOWLIST` is set. `--registry` adds one `getProgramAccounts` at start. The default RPC is mainnet, matching `alert.py`. A devnet registry read sets `SOLANA_RPC=https://api.devnet.solana.com`. Public RPC endpoints rate-limit.

```bash
SOLANA_RPC=https://api.devnet.solana.com DRY_RUN=1 \
  cargo run -- --registry <registry-pubkey>
```

`DRY_RUN` defaults to 1. `KILL` or `KILL_SWITCH=1` stops the loop. `seen.json` drops entries after 7 days.

## Verified

From this directory on 2026-11-12, with `SDKROOT` set to the Xcode macOS SDK and `CARGO_HOME` / `CARGO_TARGET_DIR` on NoxSSD:

```bash
cargo test
```

Result: 15 passed, 0 failed, exit 0. The first run, before the library existed, exited 101 because those functions were missing. `cargo run -- --help` exits 0.
