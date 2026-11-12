import type { Transaction } from "@solana/web3.js";

export type Connected = {
  publicKey: string;
  signTransaction: (tx: Transaction) => Promise<unknown>;
  source: "sdk" | "window.phantom.solana";
};

type Pub = { toString(): string };

type Injected = {
  connect: () => Promise<{ publicKey?: Pub }>;
  publicKey?: Pub;
  signTransaction: (tx: Transaction) => Promise<unknown>;
};

export type WalletWindow = {
  phantom?: { solana?: Injected };
};

export async function connectWallet(win: WalletWindow): Promise<Connected> {
  try {
    const { BrowserSDK, AddressType } = await import("@phantom/browser-sdk");
    const sdk = new BrowserSDK({
      providers: ["injected"],
      addressTypes: [AddressType.solana],
    });
    const connected = await Promise.race([
      sdk.connect({ provider: "injected" }),
      new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error("Phantom SDK timed out")), 2000);
      }),
    ]);
    const address =
      connected.addresses.find((item) => item.addressType === AddressType.solana)?.address ??
      connected.addresses[0]?.address;
    if (!address) throw new Error("Phantom SDK returned no Solana address");
    await sdk.solana.switchNetwork("devnet");
    return {
      publicKey: address,
      signTransaction: (tx) => sdk.solana.signTransaction(tx),
      source: "sdk",
    };
  } catch {
    const injected = win.phantom?.solana;
    if (!injected?.connect) throw new Error("Phantom is not available");
    const res = await injected.connect();
    const key = res?.publicKey?.toString() ?? injected.publicKey?.toString();
    if (!key) throw new Error("Phantom returned no public key");
    return {
      publicKey: key,
      signTransaction: (tx) => injected.signTransaction(tx),
      source: "window.phantom.solana",
    };
  }
}
