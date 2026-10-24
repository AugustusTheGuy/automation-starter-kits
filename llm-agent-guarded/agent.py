"""
AI Agent — Working
Same dry-run call as Standard, plus a JSON-lines trace in agent.log.
Approval is read from a terminal. A non-interactive run stays unapproved.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

LOG = Path("agent.log")
ENDPOINT = os.getenv("LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions")
KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
MAX_STEPS = int(os.getenv("MAX_STEPS", "4"))
COST_CAP_USD = float(os.getenv("COST_CAP_USD", "0.50"))
APPROVE = os.getenv("REQUIRE_APPROVE", "1") == "1"
CALL_USD = 0.002


def write_trace(event: dict):
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def approve_gate() -> bool:
    if not APPROVE:
        return True
    if os.getenv("AUTO_APPROVE", "0") == "1":
        return True
    if not sys.stdin.isatty():
        return False
    try:
        ans = input("APPROVE? (y/n) ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def call_llm(messages: list[dict]) -> str:
    if not KEY:
        return "[dry] no key — would call model"
    if COST_CAP_USD <= 0 or CALL_USD > COST_CAP_USD:
        return "[stopped] estimated cost exceeds cap"
    try:
        r = httpx.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {KEY}"},
            json={"model": MODEL, "messages": messages, "max_tokens": 400},
            timeout=60,
        )
    except httpx.HTTPError as e:
        return f"[error] {e}"
    if r.status_code >= 400:
        return f"[error] status {r.status_code}"
    try:
        text = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return "[error] bad response"
    return text or "[empty]"


def run(question: str, docs_dir: str = "docs") -> dict:
    if MAX_STEPS < 1:
        result = {"answer": "[stopped] MAX_STEPS < 1", "approved": False, "cost_cap": COST_CAP_USD}
        write_trace({"event": "stopped", "reason": "max_steps"})
        return result
    docs = ""
    p = Path(docs_dir)
    if p.exists():
        for f in list(p.glob("*.txt"))[:5]:
            docs += f.read_text(encoding="utf-8", errors="replace")[:2000] + "\n"
    messages = [
        {"role": "system", "content": "Answer only from the docs. If missing, say so."},
        {"role": "user", "content": f"Docs:\n{docs}\n\nQ: {question}"},
    ]
    write_trace({"step": 1, "action": "retrieve", "chars": len(docs)})
    answer = call_llm(messages)
    write_trace({"step": 2, "action": "answer", "preview": answer[:200]})
    approved = approve_gate()
    write_trace({"step": 3, "action": "await_approve", "approved": approved})
    return {"answer": answer, "approved": approved, "cost_cap": COST_CAP_USD}


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "What does this product do?"
    print(json.dumps(run(q), indent=2))
