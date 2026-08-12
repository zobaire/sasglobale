"""Lydia Web UI bridge — serves UI and bridges backend events + memories."""
from __future__ import annotations
import asyncio
import json
import threading
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from brain.config import load_config, get_providers, set_active_provider
from brain.events import register
from brain.memory import Memory
from brain.battery import start as start_battery, get_latest
from brain.schedule import (
    start as start_schedule,
    list_events as schedule_list_events,
    add_event as schedule_add_event,
    update_event as schedule_update_event,
    delete_event as schedule_delete_event,
)
from brain.main import (
    process_request,
    abort_all,
    is_stop_command,
    toggle_mute,
    is_muted,
    speak_streamed_if_unmuted,
    interrupt_and_speak,
    handle_wake,
)

_UI_DIR = Path(__file__).parent.parent / "ui"
_MEMORY_DIR = Path(__file__).parent.parent / "memory_data"
_ENV_FILE = Path(__file__).parent.parent / ".env"

app = FastAPI(title="Lydia")
_clients: list[WebSocket] = []
_loop: asyncio.AbstractEventLoop | None = None
_listening_enabled = True


@app.on_event("startup")
async def _capture_loop() -> None:
    global _loop
    _loop = asyncio.get_running_loop()


def _load_env() -> dict[str, str]:
    env = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# --- Memory helpers ---

def _load_routines() -> list[dict]:
    routines_dir = _MEMORY_DIR / "routines"
    routines: list[dict] = []
    if routines_dir.exists():
        for rf in sorted(routines_dir.glob("*.json")):
            try:
                d = json.loads(rf.read_text(encoding="utf-8"))
                if d.get("name"):
                    routines.append(d)
            except Exception:
                pass
    return routines


def _load_notes() -> str:
    path = _MEMORY_DIR / "notes.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _get_effort_tier() -> str:
    path = _MEMORY_DIR / "effort.json"
    if path.exists():
        try:
            return json.loads(path.read_text()).get("tier", "balanced")
        except Exception:
            pass
    return "balanced"


# --- Broadcast ---

def _translate_event(evt: dict) -> dict | None:
    t = evt.get("type", "")
    if t == "response":
        return {"type": "assistant", "text": evt.get("text", "")}
    elif t == "status":
        msg = evt.get("message", "")
        mapping = {
            "Thinking...": "thinking",
            "Speaking...": "talking",
            "Listening...": "listening",
            "Wake.": "listening",
            "Ready.": "connected",
            "Stopped.": "connected",
        }
        return {"type": "status", "text": mapping.get(msg, "connected")}
    elif t == "user":
        return {"type": "user", "text": evt.get("text", "")}
    elif t == "tool":
        return {"type": "tool", "name": evt.get("name", ""), "args": evt.get("args", {})}
    elif t == "tool_result":
        return {"type": "tool_result", "name": evt.get("name", ""), "text": evt.get("result", "")}
    elif t == "mute":
        return {"type": "mute", "muted": evt.get("muted", False)}
    elif t == "provider_changed":
        return {"type": "provider", "name": evt.get("provider", "")}
    elif t == "schedule":
        return {"type": "schedule", "events": evt.get("events", [])}
    elif t == "reminder":
        return {"type": "reminder", "text": evt.get("text", ""), "event": evt.get("event", "")}
    return evt


def broadcast_to_ws(event: dict) -> None:
    evt = _translate_event(event)
    if evt is None or _loop is None or _loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(_async_broadcast(evt), _loop)
    except RuntimeError:
        pass


async def _async_broadcast(event: dict) -> None:
    data = json.dumps(event)
    for ws in list(_clients):
        try:
            await ws.send_text(data)
        except Exception:
            if ws in _clients:
                _clients.remove(ws)


# --- Static UI ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((_UI_DIR / "index.html").read_text(encoding="utf-8"))


_vendor_dir = _UI_DIR / "vendor"
if _vendor_dir.exists():
    app.mount("/vendor", StaticFiles(directory=str(_vendor_dir)), name="vendor")


# --- Battery / Balance API ---

@app.get("/api/battery")
async def api_battery():
    """Return provider balances/rate-limits for the UI meters."""
    latest = get_latest()
    if latest:
        return latest
    env = _load_env()
    result = {}
    if env.get("DEEPSEEK_API_KEY", ""):
        result["deepseek"] = {"pct": 50, "currency": "USD", "amount": 0, "available": True}
    if env.get("KIMI_API_KEY", ""):
        result["kimi"] = {"pct": 50, "currency": "USD", "amount": 0, "available": True}
    if env.get("GROQ_API_KEY", ""):
        result["groq"] = {"pct": 50, "remaining": 0, "limit": 0, "available": True}
    return result


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)

    memory = Memory()
    await ws.send_text(json.dumps({"type": "state",
        "routines": _load_routines(),
        "notes": _load_notes(),
    }))
    await ws.send_text(json.dumps({"type": "effort", "tier": _get_effort_tier()}))
    await ws.send_text(json.dumps({"type": "lang", "lang": "en", "name": "English"}))
    await ws.send_text(json.dumps({"type": "mute", "muted": is_muted()}))
    await ws.send_text(json.dumps({"type": "schedule", "events": schedule_list_events()}))
    initial_batt = get_latest()
    if initial_batt:
        await ws.send_text(json.dumps({"type": "battery", **initial_batt}))

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "user_text":
                text = msg.get("text", "").strip()
                if not text:
                    continue
                if is_stop_command(text):
                    abort_all()
                    await ws.send_text(json.dumps({"type": "assistant", "text": "Stopped."}))
                    continue
                loop = asyncio.get_event_loop()
                try:
                    response = await loop.run_in_executor(None, process_request, text)
                    # Newest message wins: interrupt any current speech, then speak.
                    threading.Thread(target=interrupt_and_speak, args=(response,), daemon=True).start()
                except Exception as e:
                    await ws.send_text(json.dumps({"type": "assistant", "text": f"Error: {e}"}))

            elif msg_type == "wake":
                await ws.send_text(json.dumps({"type": "status", "text": "listening"}))
                def _run_mic_pipeline():
                    try:
                        handle_wake()
                    except Exception as e:
                        print(f"[Mic] Error: {e}")
                threading.Thread(target=_run_mic_pipeline, daemon=True).start()

            elif msg_type == "stop":
                abort_all()
                await ws.send_text(json.dumps({"type": "status", "text": "connected"}))

            elif msg_type == "set_lang":
                lang = msg.get("lang", "en")
                name = "中文" if lang == "zh" else "English"
                import os
                os.environ["LYDIA_LANG"] = lang
                await ws.send_text(json.dumps({"type": "lang", "lang": lang, "name": name}))

            elif msg_type == "set_effort":
                tier = msg.get("tier", "balanced")
                provider_map = {
                    "snappy": "groq",
                    "balanced": "kimi",
                    "max": "deepseek",
                    "ultra": "deepseek",
                }
                provider = provider_map.get(tier, "kimi")
                set_active_provider(provider)
                try:
                    (_MEMORY_DIR / "effort.json").write_text(
                        json.dumps({"tier": tier}), encoding="utf-8")
                except Exception:
                    pass
                await ws.send_text(json.dumps({"type": "effort", "tier": tier}))

            elif msg_type == "set_mute":
                try:
                    muted = msg.get("muted", False)
                    if muted != is_muted():
                        toggle_mute()
                    await ws.send_text(json.dumps({"type": "mute", "muted": is_muted()}))
                except Exception as e:
                    print(f"[WS] set_mute error: {e}")
                    await ws.send_text(json.dumps({"type": "mute", "muted": is_muted()}))

            elif msg_type == "set_listen":
                global _listening_enabled
                _listening_enabled = msg.get("listening", True)
                if not _listening_enabled:
                    from brain.wake import pause_wake_mic
                    pause_wake_mic()
                else:
                    from brain.wake import resume_wake_mic
                    resume_wake_mic()
                await ws.send_text(json.dumps({"type": "listen", "listening": _listening_enabled}))

            elif msg_type == "schedule_list":
                await ws.send_text(json.dumps({"type": "schedule", "events": schedule_list_events()}))

            elif msg_type == "schedule_add":
                title = msg.get("title", "").strip()
                date = msg.get("date", "").strip()
                if title and date:
                    evt = schedule_add_event(title, date)
                    await ws.send_text(json.dumps({"type": "schedule_msg", "text": f"✅ Added: {evt['title']} at {evt['date']}"}))
                else:
                    await ws.send_text(json.dumps({"type": "schedule_msg", "text": "Need a title and a date (YYYY-MM-DD HH:MM)."}))

            elif msg_type == "schedule_update":
                updated = schedule_update_event(
                    msg.get("id", ""),
                    title=msg.get("title"),
                    date=msg.get("date"),
                )
                await ws.send_text(json.dumps({"type": "schedule_msg",
                    "text": f"✅ Updated: {updated['title']} at {updated['date']}" if updated else "Event not found."}))

            elif msg_type == "schedule_delete":
                ok = schedule_delete_event(msg.get("id", ""))
                await ws.send_text(json.dumps({"type": "schedule_msg",
                    "text": "🗑️ Event cancelled." if ok else "Event not found."}))

    except WebSocketDisconnect:
        if ws in _clients:
            _clients.remove(ws)


def start_web_background(port: int = 8765, host: str = "0.0.0.0") -> None:
    register(broadcast_to_ws)
    start_battery()
    start_schedule()

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
