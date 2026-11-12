import { describe, expect, it, vi } from "vitest";
import { connectWallet } from "../src/wallet";

vi.mock("@phantom/browser-sdk", () => ({
  AddressType: { solana: "Solana" },
  BrowserSDK: class {
    connect() {
      return Promise.reject(new Error("no extension"));
    }
  },
}));

describe("connectWallet", () => {
  it("uses window.phantom.solana when the SDK connect fails", async () => {
    const key = "11111111111111111111111111111111";
    const connected = await connectWallet({
      phantom: {
        solana: {
          connect: async () => ({ publicKey: { toString: () => key } }),
          signTransaction: async (tx) => tx,
        },
      },
    });
    expect(connected.publicKey).toBe(key);
    expect(connected.source).toBe("window.phantom.solana");
  });
});
