"""
llm_client.py -- the "brain" of the LLM layer (provider-agnostic).

Takes a market brief (from market_brief.py) and returns a structured decision:
    {"action": "take"|"skip", "confidence": 0-1, "reason": "..."}

Three modes so we can build and test WITHOUT spending money or needing network:
  * mock      : a deterministic offline stand-in (no key, no network). Used to
                test the whole pipeline now and as a safe fallback.
  * deepseek  : OpenAI-compatible REST call to https://api.deepseek.com
                (your server -- this sandbox blocks it).
  * anthropic : native Claude call to https://api.anthropic.com (reachable here).

Uses only the standard library for HTTP (urllib), so no SDK install is needed.
Network/parse failures fall back to a safe "skip" with the reason recorded --
the bot must never trade on a broken brain.

CLI:  python3 llm_client.py           # runs the mock end-to-end on real data
      LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=... python3 llm_client.py --live
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

SYSTEM_PROMPT = (
    "You are a disciplined trading risk filter. You are given an ANONYMISED "
    "market brief describing a candidate setup in relative terms (trend, range "
    "position, volatility, relative volume, and the setup's reward:risk in R). "
    "You cannot predict price and must not try. Your only job: decide whether "
    "this setup is worth taking or should be skipped, based on whether the "
    "context supports it. Reply ONLY with compact JSON: "
    '{"action":"take"|"skip","confidence":0.0-1.0,"reason":"short"}. '
    "Prefer skip when context is weak, conflicting, or volume is low."
)


def _safe_skip(reason):
    return {"action": "skip", "confidence": 0.0, "reason": reason}


# ---------------------------------------------------------------------------
# mock brain: deterministic, offline. A transparent heuristic, NOT an LLM --
# just enough to exercise the pipeline and act as a fallback.
# ---------------------------------------------------------------------------
def _mock_decide(brief):
    s = brief.get("setup")
    ctx = brief.get("context", {})
    if not s or not s.get("at_entry_zone"):
        return _safe_skip("no armed setup")
    reasons = []
    score = 0.5
    # fade works better with enough reward and a real (not tiny) leg
    if s.get("reward_risk", 0) >= 1.0:
        score += 0.1; reasons.append("rr>=1")
    if s.get("leg_pct", 0) >= 3.0:
        score += 0.1; reasons.append("clean leg")
    # our volume finding: very low volume -> moves too small, skip chop
    rv = ctx.get("rel_volume")
    if rv is not None and rv < 0.6:
        score -= 0.2; reasons.append("low volume")
    action = "take" if score >= 0.55 else "skip"
    return {"action": action, "confidence": round(min(max(score, 0), 1), 2),
            "reason": "mock: " + (", ".join(reasons) or "weak context")}


# ---------------------------------------------------------------------------
# real providers (only used with --live and a key present)
# ---------------------------------------------------------------------------
def _post(url, headers, payload, timeout=30):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _parse_json_reply(txt):
    txt = txt.strip()
    if "```" in txt:                       # strip markdown fences if present
        txt = txt.split("```")[1].replace("json", "", 1).strip()
    start, end = txt.find("{"), txt.rfind("}")
    if start < 0 or end < 0:
        return _safe_skip("unparseable reply")
    try:
        d = json.loads(txt[start:end + 1])
    except json.JSONDecodeError:
        return _safe_skip("bad json")
    if d.get("action") not in ("take", "skip"):
        return _safe_skip("no valid action")
    d.setdefault("confidence", 0.5)
    d.setdefault("reason", "")
    return d


def _deepseek_decide(brief, model="deepseek-chat"):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return _safe_skip("no DEEPSEEK_API_KEY")
    try:
        resp = _post("https://api.deepseek.com/chat/completions",
                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     {"model": model, "temperature": 0.2,
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": brief["text"]}]})
        return _parse_json_reply(resp["choices"][0]["message"]["content"])
    except (urllib.error.URLError, KeyError, TimeoutError) as e:
        return _safe_skip(f"deepseek error: {e}")


def _anthropic_decide(brief, model="claude-sonnet-5"):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _safe_skip("no ANTHROPIC_API_KEY")
    try:
        resp = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01",
                      "Content-Type": "application/json"},
                     {"model": model, "max_tokens": 200, "temperature": 0.2,
                      "system": SYSTEM_PROMPT,
                      "messages": [{"role": "user", "content": brief["text"]}]})
        return _parse_json_reply(resp["content"][0]["text"])
    except (urllib.error.URLError, KeyError, TimeoutError) as e:
        return _safe_skip(f"anthropic error: {e}")


def decide(brief, provider="mock"):
    """Route to a provider. Any failure returns a safe skip -- never crash the
    bot, never trade on a broken brain."""
    if provider == "mock":
        return _mock_decide(brief)
    if provider == "deepseek":
        return _deepseek_decide(brief)
    if provider == "anthropic":
        return _anthropic_decide(brief)
    return _safe_skip(f"unknown provider {provider}")


if __name__ == "__main__":
    import sys
    from market_brief import build_brief
    from data_loader import load_ohlcv

    provider = os.environ.get("LLM_PROVIDER", "mock")
    if "--live" not in sys.argv:
        provider = "mock"
    print(f"LLM client demo -- provider: {provider}\n")

    df = load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")
    shown = 0
    for end in range(400, len(df)):
        brief = build_brief(df.iloc[:end])
        if brief["setup"] and brief["setup"]["at_entry_zone"]:
            d = decide(brief, provider=provider)
            print("-" * 60)
            print(brief["text"])
            print(f">>> DECISION: {d['action'].upper()}  "
                  f"(confidence {d['confidence']})  -- {d['reason']}")
            shown += 1
            if shown >= 5:
                break
