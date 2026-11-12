import {
  PublicKey,
  SystemProgram,
  TransactionInstruction,
  type AccountMeta,
} from "@solana/web3.js";

export const PROGRAM_ID = new PublicKey("Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3");
export const DEVNET_RPC = "https://api.devnet.solana.com";

const INIT = Uint8Array.from([131, 22, 4, 103, 24, 94, 163, 239]);
const ADD = Uint8Array.from([46, 204, 2, 157, 62, 4, 247, 72]);
const REMOVE = Uint8Array.from([63, 90, 140, 178, 113, 251, 150, 66]);
const PAUSE = Uint8Array.from([91, 60, 125, 192, 176, 225, 166, 218]);
export const WATCH_ENTRY_DISC = Uint8Array.from([126, 80, 144, 98, 34, 115, 191, 6]);

const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

export function b58encode(raw: Uint8Array): string {
  let n = 0n;
  for (const byte of raw) n = n * 256n + BigInt(byte);
  let body = "";
  while (n > 0n) {
    body = B58[Number(n % 58n)] + body;
    n /= 58n;
  }
  let pad = 0;
  for (const byte of raw) {
    if (byte !== 0) break;
    pad += 1;
  }
  return "1".repeat(pad) + body;
}

export function registryPda(authority: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("registry"), authority.toBuffer()],
    PROGRAM_ID,
  )[0];
}

export function watchPda(registry: PublicKey, target: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("watch"), registry.toBuffer(), target.toBuffer()],
    PROGRAM_ID,
  )[0];
}

function build(data: Buffer, keys: AccountMeta[]): TransactionInstruction {
  return new TransactionInstruction({ programId: PROGRAM_ID, keys, data });
}

export function initRegistryIx(authority: PublicKey): TransactionInstruction {
  return build(Buffer.from(INIT), [
    { pubkey: registryPda(authority), isSigner: false, isWritable: true },
    { pubkey: authority, isSigner: true, isWritable: true },
    { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
  ]);
}

export function addWatchIx(
  authority: PublicKey,
  target: PublicKey,
  minLamports: number,
  mint: PublicKey,
): TransactionInstruction {
  const data = Buffer.alloc(48);
  Buffer.from(ADD).copy(data, 0);
  data.writeBigUInt64LE(BigInt(minLamports), 8);
  Buffer.from(mint.toBuffer()).copy(data, 16);
  const registry = registryPda(authority);
  return build(data, [
    { pubkey: registry, isSigner: false, isWritable: true },
    { pubkey: watchPda(registry, target), isSigner: false, isWritable: true },
    { pubkey: authority, isSigner: true, isWritable: true },
    { pubkey: target, isSigner: false, isWritable: false },
    { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
  ]);
}

export function removeWatchIx(authority: PublicKey, target: PublicKey): TransactionInstruction {
  const registry = registryPda(authority);
  return build(Buffer.from(REMOVE), [
    { pubkey: registry, isSigner: false, isWritable: false },
    { pubkey: watchPda(registry, target), isSigner: false, isWritable: true },
    { pubkey: authority, isSigner: true, isWritable: true },
  ]);
}

export function setPausedIx(authority: PublicKey, paused: boolean): TransactionInstruction {
  const data = Buffer.alloc(9);
  Buffer.from(PAUSE).copy(data, 0);
  data[8] = paused ? 1 : 0;
  return build(data, [
    { pubkey: registryPda(authority), isSigner: false, isWritable: true },
    { pubkey: authority, isSigner: true, isWritable: false },
  ]);
}

export function targetFromAccountData(data: Uint8Array): string | null {
  if (data.length < 72) return null;
  const disc = data.subarray(0, 8);
  for (let i = 0; i < WATCH_ENTRY_DISC.length; i += 1) {
    if (disc[i] !== WATCH_ENTRY_DISC[i]) return null;
  }
  return new PublicKey(data.subarray(40, 72)).toBase58();
}
