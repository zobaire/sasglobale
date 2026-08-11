"""API integrations: Spotify, Discord, Tebex."""
from __future__ import annotations
import json
import time
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"
_MEMORY_DIR = _REPO_ROOT / "memory_data"


def _load_env() -> dict[str, str]:
    env = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# --- Spotify ---

def spotify_control(action: str) -> str:
    """Control Spotify playback: play, pause, next, previous."""
    env = _load_env()
    client_id = env.get("SPOTIFY_CLIENT_ID", "")
    client_secret = env.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return "Spotify not configured — missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET."

    token_path = _MEMORY_DIR / "spotify_token.json"
    refresh_token = ""
    if token_path.exists():
        try:
            refresh_token = json.loads(token_path.read_text()).get("refresh_token", "")
        except Exception:
            pass

    if not refresh_token:
        return "Spotify not authenticated. Need OAuth refresh token."

    try:
        r = requests.post("https://accounts.spotify.com/api/token", data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }, auth=(client_id, client_secret), timeout=15)
        if r.status_code != 200:
            return f"Spotify auth failed: {r.status_code}"
        access_token = r.json()["access_token"]
    except Exception as e:
        return f"Spotify auth error: {e}"

    headers = {"Authorization": f"Bearer {access_token}"}
    action = action.lower().strip()

    endpoints = {
        "play": ("PUT", "https://api.spotify.com/v1/me/player/play"),
        "resume": ("PUT", "https://api.spotify.com/v1/me/player/play"),
        "pause": ("PUT", "https://api.spotify.com/v1/me/player/pause"),
        "next": ("POST", "https://api.spotify.com/v1/me/player/next"),
        "previous": ("POST", "https://api.spotify.com/v1/me/player/previous"),
    }

    if action not in endpoints:
        return f"Unknown Spotify action: {action}. Use play, pause, next, previous."

    method, url = endpoints[action]
    try:
        if method == "PUT":
            r = requests.put(url, headers=headers, timeout=10)
        else:
            r = requests.post(url, headers=headers, timeout=10)
        if r.status_code in (200, 202, 204):
            return f"Spotify: {action} OK"
        return f"Spotify {action}: {r.status_code}"
    except Exception as e:
        return f"Spotify error: {e}"


# --- Discord ---

def discord_check() -> str:
    """Check Discord server status."""
    env = _load_env()
    token = env.get("DISCORD_BOT_TOKEN", "")
    guild_id = env.get("DISCORD_GUILD_ID", "")
    if not token or not guild_id:
        return "Discord not configured."

    headers = {"Authorization": f"Bot {token}"}
    try:
        r = requests.get(
            f"https://discord.com/api/v10/guilds/{guild_id}?with_counts=true",
            headers=headers, timeout=15)
        if r.status_code != 200:
            return f"Discord API error: {r.status_code}"
        data = r.json()
        return (
            f"Discord: {data.get('name', 'Server')}\n"
            f"- Members: {data.get('approximate_member_count', '?')}\n"
            f"- Online: {data.get('approximate_presence_count', '?')}"
        )
    except Exception as e:
        return f"Discord error: {e}"


# --- Tebex ---

def tebex_check() -> str:
    """Check Tebex store for recent sales."""
    env = _load_env()
    secret = env.get("TEBEX_SECRET", "")
    if not secret:
        return "Tebex not configured."

    secret = secret.replace("sv_tebexSecret ", "").strip()
    headers = {"X-Tebex-Secret": secret}

    try:
        r = requests.get("https://plugin.tebex.io/payments?limit=5",
                         headers=headers, timeout=15)
        if r.status_code != 200:
            return f"Tebex API error: {r.status_code}"

        data = r.json()
        payments = data if isinstance(data, list) else data.get("data", [])
        if not payments:
            return "Tebex (SAS Scripts): No recent payments."

        state_path = _MEMORY_DIR / "store_state.json"
        last_id = 0
        if state_path.exists():
            try:
                last_id = json.loads(state_path.read_text()).get("last_payment_id", 0)
            except Exception:
                pass

        new_count = sum(1 for p in payments if p.get("id", 0) > last_id)
        if payments:
            state_path.write_text(json.dumps({
                "last_payment_id": max(p["id"] for p in payments),
                "last_check": time.time(),
            }))

        lines = [f"Tebex (SAS Scripts): {len(payments)} recent payments"]
        for p in payments[:5]:
            player = p.get("player", {}).get("name", "Unknown")
            pkgs = [pkg.get("name", "?") for pkg in p.get("packages", [])]
            amount = p.get("amount", 0)
            try:
                amount_f = float(amount)
            except (TypeError, ValueError):
                amount_f = 0.0
            currency = None
            cur = p.get("currency")
            if isinstance(cur, dict):
                currency = cur.get("symbol") or cur.get("iso_4217", "USD")
            elif cur:
                currency = str(cur)
            currency = currency or "USD"
            date = str(p.get("date", ""))[:10]
            is_new = " *" if p.get("id", 0) > last_id else ""
            lines.append(f"  {date}: {player} — {', '.join(pkgs)} ({currency} {amount_f:.2f}){is_new}")

        if new_count:
            lines.append(f"\n{new_count} new sale(s)!")

        return "\n".join(lines)
    except Exception as e:
        return f"Tebex error: {e}"


def check_business() -> str:
    """Check both Discord and Tebex — 'what's new' command."""
    d = discord_check()
    t = tebex_check()
    return f"{d}\n\n{t}"
