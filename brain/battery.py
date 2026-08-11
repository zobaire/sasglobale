"""Provider balance / rate-limit polling for the UI battery meters."""
from __future__ import annotations
import threading
import time

import requests

from brain.config import get_providers
from brain.events import broadcast

_POLL_SECONDS = 30
_LATEST: dict[str, dict] = {}


def _num(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _poll_groq(provider: dict) -> dict | None:
    key = provider.get("api_key", "")
    if not key:
        return None
    try:
        r = requests.post(
            provider["base_url"].rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": provider.get("model", ""),
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            },
            timeout=10,
        )
        h = r.headers
        limit_t = _num(h.get("x-ratelimit-limit-tokens"))
        rem_t = _num(h.get("x-ratelimit-remaining-tokens"))
        limit_r = _num(h.get("x-ratelimit-limit-requests"))
        rem_r = _num(h.get("x-ratelimit-remaining-requests"))
        if r.status_code == 429:
            return {
                "pct": 0,
                "remaining": 0,
                "limit": limit_t or 0,
                "available": True,
            }
        pcts = []
        if limit_t and rem_t is not None:
            pcts.append(rem_t / limit_t * 100)
        if limit_r and rem_r is not None:
            pcts.append(rem_r / limit_r * 100)
        if pcts:
            return {
                "pct": max(0, min(100, round(min(pcts)))),
                "remaining": rem_t if rem_t is not None else 0,
                "limit": limit_t or 0,
                "available": True,
            }
    except Exception:
        pass
    return None


def _poll_deepseek(provider: dict) -> dict | None:
    key = provider.get("api_key", "")
    if not key:
        return None
    try:
        r = requests.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            bi = (data.get("balance_infos") or [{}])[0]
            amount = float(bi.get("total_balance", 0))
            return {
                "pct": 100 if amount > 0 else 0,
                "currency": bi.get("currency", "USD"),
                "amount": amount,
                "available": True,
            }
    except Exception:
        pass
    return None


def _poll_kimi(provider: dict) -> dict | None:
    key = provider.get("api_key", "")
    if not key:
        return None
    base = provider.get("base_url", "https://api.moonshot.cn/v1").rstrip("/")
    url = base + "/users/me/balance"
    try:
        r = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            d = data.get("data") or {}
            amount = float(d.get("available_balance", 0))
            return {
                "pct": 100 if amount > 0 else 0,
                "currency": "USD",
                "amount": amount,
                "available": amount > 0,
            }
    except Exception:
        pass
    return None


_POLLERS = {
    "groq": _poll_groq,
    "deepseek": _poll_deepseek,
    "kimi": _poll_kimi,
}


def _loop() -> None:
    while True:
        try:
            providers = get_providers()
            result: dict[str, dict] = {}
            for key, provider in providers.items():
                poller = _POLLERS.get(key)
                if not poller:
                    continue
                data = poller(provider)
                if data is not None:
                    result[key] = data
                    _LATEST[key] = data
            if result:
                broadcast({"type": "battery", **result})
        except Exception:
            pass
        time.sleep(_POLL_SECONDS)


def start() -> None:
    """Start the background battery poller thread."""
    threading.Thread(target=_loop, daemon=True).start()


def get_latest() -> dict[str, dict]:
    """Return the most recently cached battery data for the REST endpoint."""
    return dict(_LATEST)
