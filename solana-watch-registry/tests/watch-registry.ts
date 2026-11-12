import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { WatchRegistry } from "../target/types/watch_registry";
import { expect } from "chai";

describe("watch-registry", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.WatchRegistry as Program<WatchRegistry>;
  const authority = provider.wallet.publicKey;

  const registryPda = (auth: anchor.web3.PublicKey) =>
    anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("registry"), auth.toBuffer()],
      program.programId,
    );

  const watchPda = (registry: anchor.web3.PublicKey, target: anchor.web3.PublicKey) =>
    anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("watch"), registry.toBuffer(), target.toBuffer()],
      program.programId,
    );

  const accountsForAdd = (
    registry: anchor.web3.PublicKey,
    entry: anchor.web3.PublicKey,
    auth: anchor.web3.PublicKey,
    target: anchor.web3.PublicKey,
  ) => ({
    registry,
    entry,
    authority: auth,
    target,
    systemProgram: anchor.web3.SystemProgram.programId,
  });

  it("inits a registry and adds a watch", async () => {
    const [registry] = registryPda(authority);
    await program.methods
      .initRegistry()
      .accounts({
        registry,
        authority,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();
    const target = anchor.web3.Keypair.generate().publicKey;
    const [entry] = watchPda(registry, target);
    await program.methods
      .addWatch(new anchor.BN(1_000_000), anchor.web3.PublicKey.default)
      .accounts(accountsForAdd(registry, entry, authority, target))
      .rpc();
    const row = await program.account.watchEntry.fetch(entry);
    expect(row.minLamports.toNumber()).to.equal(1_000_000);
    expect(row.target.toBase58()).to.equal(target.toBase58());
  });

  it("rejects a second signer", async () => {
    const [registry] = registryPda(authority);
    const other = anchor.web3.Keypair.generate();
    const sig = await provider.connection.requestAirdrop(other.publicKey, 1_000_000_000);
    await provider.connection.confirmTransaction(sig);
    const target = anchor.web3.Keypair.generate().publicKey;
    const [entry] = watchPda(registry, target);
    try {
      await program.methods
        .addWatch(new anchor.BN(1), anchor.web3.PublicKey.default)
        .accounts(accountsForAdd(registry, entry, other.publicKey, target))
        .signers([other])
        .rpc();
      expect.fail("other authority was accepted");
    } catch (err) {
      expect(String(err)).to.match(/ConstraintSeeds|ConstraintHasOne|2006|0x7d6/i);
    }
  });

  it("rejects a duplicate watch pda", async () => {
    const [registry] = registryPda(authority);
    const target = anchor.web3.Keypair.generate().publicKey;
    const [entry] = watchPda(registry, target);
    const mint = anchor.web3.PublicKey.default;
    await program.methods
      .addWatch(new anchor.BN(2), mint)
      .accounts(accountsForAdd(registry, entry, authority, target))
      .rpc();
    try {
      await program.methods
        .addWatch(new anchor.BN(3), mint)
        .accounts(accountsForAdd(registry, entry, authority, target))
        .rpc();
      expect.fail("duplicate pda was accepted");
    } catch (err) {
      expect(String(err)).to.match(/already in use/i);
    }
  });

  it("rejects add while paused, then accepts remove after unpause", async () => {
    const [registry] = registryPda(authority);
    await program.methods.setPaused(true).accounts({ registry, authority }).rpc();
    const blocked = anchor.web3.Keypair.generate().publicKey;
    const [blockedEntry] = watchPda(registry, blocked);
    try {
      await program.methods
        .addWatch(new anchor.BN(4), anchor.web3.PublicKey.default)
        .accounts(accountsForAdd(registry, blockedEntry, authority, blocked))
        .rpc();
      expect.fail("paused add was accepted");
    } catch (err) {
      expect(String(err)).to.match(/paused/i);
    }
    await program.methods.setPaused(false).accounts({ registry, authority }).rpc();
    const target = anchor.web3.Keypair.generate().publicKey;
    const [entry] = watchPda(registry, target);
    await program.methods
      .addWatch(new anchor.BN(5), anchor.web3.PublicKey.default)
      .accounts(accountsForAdd(registry, entry, authority, target))
      .rpc();
    await program.methods.removeWatch().accounts({ registry, entry, authority }).rpc();
    try {
      await program.account.watchEntry.fetch(entry);
      expect.fail("closed entry still fetched");
    } catch (err) {
      expect(String(err)).to.match(/Account does not exist|not found/i);
    }
  });
});
