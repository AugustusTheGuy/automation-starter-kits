import { Buffer } from "buffer";
import { Connection, PublicKey, Transaction } from "@solana/web3.js";

globalThis.Buffer = Buffer;
import {
  DEVNET_RPC,
  PROGRAM_ID,
  WATCH_ENTRY_DISC,
  addWatchIx,
  b58encode,
  initRegistryIx,
  registryPda,
  removeWatchIx,
  setPausedIx,
  targetFromAccountData,
} from "./instructions";
import { connectWallet, type Connected, type WalletWindow } from "./wallet";

const connection = new Connection(DEVNET_RPC, "confirmed");
let session: Connected | null = null;
let lastTx: Transaction | null = null;

const statusEl = document.querySelector("#status") as HTMLElement;
const simEl = document.querySelector("#sim") as HTMLElement;
const listEl = document.querySelector("#watches") as HTMLElement;
const signBtn = document.querySelector("#sign") as HTMLButtonElement;

function authority(): PublicKey {
  if (!session) throw new Error("Connect Phantom first");
  return new PublicKey(session.publicKey);
}

function targetKey(): PublicKey {
  return new PublicKey((document.querySelector("#target") as HTMLInputElement).value.trim());
}

async function simulate(ix: ReturnType<typeof initRegistryIx>) {
  const payer = authority();
  const { blockhash } = await connection.getLatestBlockhash();
  const tx = new Transaction({ recentBlockhash: blockhash, feePayer: payer }).add(ix);
  const sim = await connection.simulateTransaction(tx);
  lastTx = tx;
  const err = sim.value.err === null ? "null" : JSON.stringify(sim.value.err);
  simEl.textContent = `err: ${err}`;
  signBtn.disabled = sim.value.err !== null;
}

document.querySelector("#connect")?.addEventListener("click", async () => {
  try {
    session = await connectWallet(window as WalletWindow);
    statusEl.textContent = `${session.publicKey} via ${session.source}`;
  } catch (err) {
    statusEl.textContent = err instanceof Error ? err.message : "connect failed";
  }
});

document.querySelector("#refresh")?.addEventListener("click", async () => {
  const registry = registryPda(authority());
  const rows = await connection.getProgramAccounts(PROGRAM_ID, {
    filters: [
      { memcmp: { offset: 0, bytes: b58encode(WATCH_ENTRY_DISC) } },
      { memcmp: { offset: 8, bytes: registry.toBase58() } },
    ],
  });
  listEl.replaceChildren();
  if (rows.length === 0) {
    listEl.textContent = "none";
    return;
  }
  for (const row of rows) {
    const target = targetFromAccountData(row.account.data);
    const item = document.createElement("li");
    item.textContent = target ?? row.pubkey.toBase58();
    listEl.append(item);
  }
});

async function onClick(fn: () => Promise<void>) {
  try {
    await fn();
  } catch (err) {
    simEl.textContent = err instanceof Error ? err.message : "request failed";
    signBtn.disabled = true;
  }
}

document.querySelector("#simulate-add")?.addEventListener("click", () =>
  onClick(async () => {
    const min = Number((document.querySelector("#min") as HTMLInputElement).value);
    await simulate(addWatchIx(authority(), targetKey(), min, PublicKey.default));
  }),
);

document.querySelector("#simulate-pause")?.addEventListener("click", () =>
  onClick(() => simulate(setPausedIx(authority(), true))),
);

document.querySelector("#simulate-remove")?.addEventListener("click", () =>
  onClick(() => simulate(removeWatchIx(authority(), targetKey()))),
);

signBtn.addEventListener("click", async () => {
  if (!session || !lastTx) return;
  await session.signTransaction(lastTx);
  simEl.textContent = `${simEl.textContent}\nsigned`;
});
