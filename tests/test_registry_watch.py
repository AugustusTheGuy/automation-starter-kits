"""Mocked RPC test for alert.py --registry. No network and no keypair."""
import asyncio
import base64
import hashlib
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM = "11111111111111111111111111111111"
DISC = bytes([126, 80, 144, 98, 34, 115, 191, 6])


def load_alert():
    path = os.path.join(ROOT, "solana-wallet-alerts", "alert.py")
    spec = importlib.util.spec_from_file_location("solana_wallet_alerts_alert", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def entry_b64(target: bytes) -> str:
    data = DISC + bytes(32) + target + (0).to_bytes(8, "little") + bytes(32) + bytes([1])
    return base64.b64encode(data).decode()


class RegistryWatch(unittest.TestCase):
    def test_filters_memcmp_discriminator_and_registry(self):
        m = load_alert()
        filters = m.registry_account_filters(SYSTEM)
        self.assertEqual(filters[0]["memcmp"]["offset"], 0)
        self.assertEqual(filters[1]["memcmp"]["offset"], 8)
        self.assertEqual(filters[1]["memcmp"]["bytes"], SYSTEM)
        self.assertEqual(hashlib.sha256(b"account:WatchEntry").digest()[:8], DISC)

    def test_fetch_reads_target_from_mocked_rpc(self):
        m = load_alert()
        seen = {}

        async def rpc(method, params):
            seen["method"] = method
            seen["params"] = params
            return {"result": [{"account": {"data": [entry_b64(bytes(32)), "base64"]}}]}

        targets = asyncio.run(m.fetch_registry_watches(rpc, m.REGISTRY_PROGRAM, SYSTEM))
        self.assertEqual(seen["method"], "getProgramAccounts")
        self.assertEqual(seen["params"][0], m.REGISTRY_PROGRAM)
        self.assertEqual(seen["params"][1]["encoding"], "base64")
        self.assertEqual(targets, [SYSTEM])

    def test_registry_flag_parses_without_a_keypair(self):
        m = load_alert()
        args = m.parse_args(["--registry", SYSTEM])
        self.assertEqual(args.registry, SYSTEM)
        self.assertEqual(m.parse_args([]).registry, "")


if __name__ == "__main__":
    unittest.main()
