"""Offline smoke tests for the starter kits. Run: python -m unittest discover -s tests -v"""
import importlib.util, json, os, py_compile, socket, subprocess, sys, tempfile, time, unittest, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KITS = ["web-scraper", "webhook-relay", "llm-agent-guarded", "solana-wallet-alerts", "solana-paper-watcher", "solana-paper-dashboard"]


def load(kit, mod):
    spec = importlib.util.spec_from_file_location(f"{kit}_{mod}".replace("-", "_"), os.path.join(ROOT, kit, mod + ".py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def has(*mods):
    return all(importlib.util.find_spec(m) for m in mods)


class Compile(unittest.TestCase):
    def test_all_kits_compile(self):
        for kit in KITS:
            for f in os.listdir(os.path.join(ROOT, kit)):
                if f.endswith(".py"):
                    py_compile.compile(os.path.join(ROOT, kit, f), doraise=True)


class WebhookRelay(unittest.TestCase):
    def test_health_post_and_bad_json(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        d = tempfile.mkdtemp(); out = os.path.join(d, "runs.jsonl")
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, "webhook-relay", "glue.py")],
                             env={**os.environ, "PORT": str(port), "OUT_SHEET": out}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(50):
                try: urllib.request.urlopen(base + "/health", timeout=1); break
                except OSError: time.sleep(0.1)
            self.assertEqual(json.load(urllib.request.urlopen(base + "/health")), {"ok": True})
            req = urllib.request.Request(base + "/", data=json.dumps({"text": "hi"}).encode(), headers={"Content-Type": "application/json"})
            self.assertEqual(json.load(urllib.request.urlopen(req))["echo"], "hi")
            bad = urllib.request.Request(base + "/", data=b"not json")
            with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(bad)
            self.assertEqual(e.exception.code, 400)
            self.assertEqual(json.loads(open(out).read().splitlines()[0])["echo"], "hi")
        finally:
            p.terminate(); p.wait(5)


@unittest.skipUnless(has("httpx", "bs4", "pydantic", "tenacity"), "scraper deps not installed")
class Scraper(unittest.TestCase):
    def test_block_detection(self):
        m = load("web-scraper", "scraper")
        self.assertTrue(m.blocked(403, ""))
        self.assertTrue(m.blocked(200, "<title>Just a moment...</title>"))
        self.assertFalse(m.blocked(200, "<html><title>ok</title></html>"))


@unittest.skipUnless(has("httpx"), "httpx not installed")
class Solana(unittest.TestCase):
    def test_pubkey_validation(self):
        m = load("solana-paper-dashboard", "agent_gui")
        self.assertTrue(m.valid_pubkey("11111111111111111111111111111111"))  # System Program id
        self.assertFalse(m.valid_pubkey("not-a-key"))
        self.assertFalse(m.valid_pubkey("0OIl" * 10))

    def test_watcher_refuses_live(self):
        env = {**os.environ, "LIVE": "1", "WATCH_ADDRESSES": "11111111111111111111111111111111"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "solana-paper-watcher", "agent.py")], env=env,
                           capture_output=True, text=True, timeout=20, cwd=tempfile.mkdtemp())
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
