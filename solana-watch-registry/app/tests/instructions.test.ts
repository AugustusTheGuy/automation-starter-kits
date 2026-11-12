import { Keypair, PublicKey, SystemProgram } from "@solana/web3.js";
import { describe, expect, it } from "vitest";
import {
  PROGRAM_ID,
  addWatchIx,
  initRegistryIx,
  registryPda,
  removeWatchIx,
  setPausedIx,
  watchPda,
} from "../src/instructions";

const INIT = [131, 22, 4, 103, 24, 94, 163, 239];
const ADD = [46, 204, 2, 157, 62, 4, 247, 72];
const REMOVE = [63, 90, 140, 178, 113, 251, 150, 66];
const PAUSE = [91, 60, 125, 192, 176, 225, 166, 218];

describe("instruction builders", () => {
  const authority = Keypair.generate().publicKey;
  const target = Keypair.generate().publicKey;
  const registry = PublicKey.findProgramAddressSync(
    [Buffer.from("registry"), authority.toBuffer()],
    PROGRAM_ID,
  )[0];
  const entry = PublicKey.findProgramAddressSync(
    [Buffer.from("watch"), registry.toBuffer(), target.toBuffer()],
    PROGRAM_ID,
  )[0];

  it("builds init_registry", () => {
    const ix = initRegistryIx(authority);
    expect([...ix.data]).toEqual(INIT);
    expect(ix.programId.equals(PROGRAM_ID)).toBe(true);
    expect(ix.keys.map((k) => k.pubkey.toBase58())).toEqual([
      registry.toBase58(),
      authority.toBase58(),
      SystemProgram.programId.toBase58(),
    ]);
    expect(ix.keys[1].isSigner).toBe(true);
    expect(registryPda(authority).equals(registry)).toBe(true);
  });

  it("builds add_watch with min lamports and mint", () => {
    const mint = Keypair.generate().publicKey;
    const ix = addWatchIx(authority, target, 1_000_000, mint);
    expect([...ix.data.subarray(0, 8)]).toEqual(ADD);
    expect(Number(ix.data.readBigUInt64LE(8))).toBe(1_000_000);
    expect(new PublicKey(ix.data.subarray(16, 48)).equals(mint)).toBe(true);
    expect(ix.keys.map((k) => k.pubkey.toBase58())).toEqual([
      registry.toBase58(),
      entry.toBase58(),
      authority.toBase58(),
      target.toBase58(),
      SystemProgram.programId.toBase58(),
    ]);
    expect(watchPda(registry, target).equals(entry)).toBe(true);
  });

  it("builds remove_watch without the system program", () => {
    const ix = removeWatchIx(authority, target);
    expect([...ix.data]).toEqual(REMOVE);
    expect(ix.keys).toHaveLength(3);
    expect(ix.keys.some((k) => k.pubkey.equals(SystemProgram.programId))).toBe(false);
  });

  it("builds set_paused", () => {
    const ix = setPausedIx(authority, true);
    expect([...ix.data.subarray(0, 8)]).toEqual(PAUSE);
    expect(ix.data[8]).toBe(1);
    expect(ix.data).toHaveLength(9);
    expect(ix.keys.map((k) => k.pubkey.toBase58())).toEqual([
      registry.toBase58(),
      authority.toBase58(),
    ]);
    expect(ix.keys[1].isSigner).toBe(true);
    expect(ix.keys[1].isWritable).toBe(false);
  });
});
