# solana-watch-registry

Anchor program that stores a watch list for `solana-wallet-alerts`. Devnet only.

Program id: `Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3`

`stake_fee` is not in this build.

## Run the tests

From this directory, with a new local wallet at `deploy-wallet.json` (gitignored). Do not point Anchor at `~/.config/solana/id.json`.

```bash
npm install
NO_DNA=1 anchor test
```

`anchor test` starts a local validator and stops it when the run ends. Cargo output is the `target` symlink onto NoxSSD.

## Deploy

One devnet deploy, same program id:

```bash
NO_DNA=1 anchor deploy --provider.cluster devnet
```

The provider wallet is `deploy-wallet.json`. Fund that public key from the devnet faucet. The global Solana CLI config stays on its previous cluster.

## Verified

Local tests passed on 2026-11-12. Devnet deploy has not been run.

```bash
SDKROOT="$(xcrun --sdk macosx --show-sdk-path)" \
CARGO_HOME=/Volumes/NoxSSD/Codex/watch-registry-cargo \
CARGO_TARGET_DIR=/Volumes/NoxSSD/Codex/watch-registry-target \
ANCHOR_WALLET="$PWD/deploy-wallet.json" \
NO_DNA=1 anchor test
```

Result: 4 passing (4s), exit 0. The first run exited 1 because Command Line Tools `ld` cannot link the MacOSX 27 SDK (`arm64e.x1`). The passing run set `SDKROOT` to Xcode 16.4's `MacOSX15.5.sdk`. The local validator was stopped. No Solana CLI config file was written.

Program id: `Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3`. Explorer link waits on the one devnet deploy.

## Read the list from the bot

From `automation-starter-kits`:

```bash
SOLANA_RPC=https://api.devnet.solana.com \
.venv/bin/python solana-wallet-alerts/alert.py --registry <registry-pubkey>
```

That call is `getProgramAccounts` plus a memcmp filter. It does not open a keypair. `DRY_RUN` still defaults to 1.

Verified: `.venv/bin/python -m pytest -q tests/test_registry_watch.py` → 3 passed, exit 0. `unittest discover -s tests -v` → 8 passed, exit 0.

## Browser page

`app/` is Vite + TypeScript. It connects with `@phantom/browser-sdk` (`providers: ["injected"]`) and falls back to `window.phantom.solana`. Cluster is devnet. Add, pause, and remove are simulated before the sign button enables.

```bash
cd app
npm install
npx vitest run
npx playwright test
```

Verified 2026-11-12 from `app/`: `npx tsc --noEmit` exit 0. `npx vitest run` 5 passed, exit 0. `npx playwright test` 1 passed (397ms), exit 0. The browser is the installed Google Chrome. The provider and the devnet RPC are mocked. The sign callback count stayed 0.

Devnet deploy has not run. The new deploy wallet has 0 SOL, and the public devnet RPC faucet is closed.
