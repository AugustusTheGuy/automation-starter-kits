import { expect, test } from "@playwright/test";

const PUB = "Fe2dGytY15xzbqL23RBTT9wCG85CHGtyHCuysiL93uXe";

test("mocked phantom simulates an add and does not sign", async ({ page }) => {
  await page.addInitScript((pub) => {
    const key = { toString: () => pub, toBase58: () => pub };
    (window as unknown as { __signed: number }).__signed = 0;
    (window as unknown as { phantom: unknown }).phantom = {
      solana: {
        isPhantom: true,
        publicKey: key,
        connect: async () => ({ publicKey: key }),
        signTransaction: async () => {
          (window as unknown as { __signed: number }).__signed += 1;
          throw new Error("sign should not run");
        },
      },
    };
  }, PUB);

  await page.route((url) => url.hostname === "api.devnet.solana.com", async (route) => {
    const body = route.request().postData() || "";
    const payload = body ? (JSON.parse(body) as { id?: number }) : {};
    const id = payload.id ?? 1;
    const json = (result: unknown) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ jsonrpc: "2.0", id, result }),
      });
    if (body.includes("getLatestBlockhash")) {
      return json({
        context: { slot: 1 },
        value: { blockhash: "11111111111111111111111111111111", lastValidBlockHeight: 99 },
      });
    }
    if (body.includes("simulateTransaction")) {
      return json({
        context: { slot: 1 },
        value: { err: null, logs: ["Program log: simulated"], accounts: null, unitsConsumed: 0 },
      });
    }
    return json([]);
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Connect Phantom" }).click();
  await expect(page.locator("#status")).toContainText(PUB);
  await page.locator("#target").fill(PUB);
  await page.getByRole("button", { name: "Simulate add" }).click();
  await expect(page.locator("#sim")).toContainText("err: null");
  await page.getByRole("button", { name: "List watches" }).click();
  await expect(page.locator("#watches")).toContainText("none");
  expect(await page.evaluate(() => (window as unknown as { __signed: number }).__signed)).toBe(0);
});
