"""Lydia Web UI bridge — serves UI and bridges backend events + memories."""
from __future__ import annotations
import asyncio
import json
import os
import secrets
import threading
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from brain.config import load_config, get_providers, set_active_provider, load_dotenv
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
    reset_abort,
    is_stop_command,
    toggle_mute,
    is_muted,
    speak_streamed_if_unmuted,
    interrupt_and_speak,
    handle_wake,
    Aborted,
)

_UI_DIR = Path(__file__).parent.parent / "ui"
_MEMORY_DIR = Path(__file__).parent.parent / "memory_data"
_TOKEN_PATH = _MEMORY_DIR / "web_token.txt"

app = FastAPI(title="Lydia")
_clients: list[WebSocket] = []
_loop: asyncio.AbstractEventLoop | None = None
_listening_enabled = True


def _get_web_token() -> str:
    """Return the persistent web token, generating one on first boot."""
    tok = os.environ.get("LYDIA_WEB_TOKEN", "")
    if tok:
        return tok
    if _TOKEN_PATH.exists():
        tok = _TOKEN_PATH.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(24)
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(tok, encoding="utf-8")
    return tok


def _is_loopback(client_ip: str) -> bool:
    return client_ip in ("127.0.0.1", "::1", "localhost")
# The currently-in-flight request future, so Stop can actually cancel it.
_running_future: asyncio.Future | None = None
# The actual worker thread running the request. Stop sets the sticky abort
# flag and NEVER clears it itself; the worker clears it in its own finally
# once it has fully unwound. This guarantees a fired Stop truly halts a
# background request instead of letting it keep talking later.
_running_thread: threading.Thread | None = None
_active_workers = 0
_lock = threading.Lock()


@app.on_event("startup")
async def _capture_loop() -> None:
    global _loop
    _loop = asyncio.get_running_loop()


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


def _load_remembered() -> list[dict]:
    path = _MEMORY_DIR / "remembered.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


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
        return {
            "type": "provider",
            "name": evt.get("provider", ""),
            "label": evt.get("label", ""),
            "model": evt.get("model", ""),
        }
    elif t == "schedule":
        return {"type": "schedule", "events": evt.get("events", [])}
    elif t == "reminder":
        return {"type": "reminder", "text": evt.get("text", ""), "event": evt.get("event", "")}
    elif t == "memory":
        return {"type": "memory", "text": evt.get("text", "")}
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
    return HTMLResponse((_UI_DIR / "indexV2.html").read_text(encoding="utf-8"))


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
    env = load_dotenv()
    result = {}
    # No real telemetry yet — report "unknown" (pct: None) instead of lying
    # with fake 50% meters. The UI renders null as "—".
    if env.get("DEEPSEEK_API_KEY", ""):
        result["deepseek"] = {"pct": None, "currency": "USD", "amount": 0, "available": True}
    if env.get("KIMI_API_KEY", ""):
        result["kimi"] = {"pct": None, "currency": "USD", "amount": 0, "available": True}
    if env.get("GROQ_API_KEY", ""):
        result["groq"] = {"pct": None, "remaining": 0, "limit": 0, "available": True}
    return result


_IMPORT_DIR = Path(__file__).parent.parent / "imports"


@app.get("/api/token")
async def api_token(request: Request):
    """Hand out the WS token — loopback clients only.

    When the UI is bound to 0.0.0.0 the token is what keeps LAN randos from
    driving the assistant (open apps, kill processes, shutdown…), so we never
    leak it to non-local requests. The browser page itself fetches this, then
    appends ?token= to the WebSocket URL.
    """
    client = request.client.host if request.client else ""
    if not _is_loopback(client):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return JSONResponse({"token": _get_web_token()})


@app.post("/api/import")
async def api_import(files: list[UploadFile] = File(...)):
    """Accept file uploads from the UI, save them into /imports, and log a
    memory note with the FULL path + a preview so Lydia can actually find and
    read what was dropped in (not just a bare filename)."""
    from brain.events import broadcast

    _IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[dict] = []
    errors: list[str] = []
    for f in files:
        try:
            # sanitize filename
            name = Path(f.filename or "file").name
            dest = _IMPORT_DIR / name
            data = await f.read()
            dest.write_bytes(data)
            saved.append({
                "name": name,
                "path": str(dest.resolve()),
                "size": len(data),
                "preview": _file_preview(dest, data),
            })
        except Exception as e:
            errors.append(f"{f.filename}: {e}")

    if saved:
        try:
            # notes.md is loaded into Lydia's system prompt, so record the
            # absolute address of every imported file there.
            note = _MEMORY_DIR / "notes.md"
            existing = note.read_text(encoding="utf-8") if note.exists() else ""
            lines = [existing.rstrip()] if existing.strip() else []
            for s in saved:
                line = f"- Imported file: {s['path']} (original name: {s['name']}, {s['size']} bytes)"
                if line not in existing:
                    lines.append(line)
            note.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        except Exception:
            pass

        try:
            # Structured record Lydia can read directly with read_file too.
            record_path = _MEMORY_DIR / "imported_files.json"
            records = []
            if record_path.exists():
                try:
                    records = json.loads(record_path.read_text(encoding="utf-8"))
                except Exception:
                    records = []
            records.extend(saved)
            record_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        # Surface in the UI memory graph so it's obvious what just landed.
        paths = ", ".join(s["path"] for s in saved)
        broadcast({"type": "memory", "text": f"Imported file(s): {paths}"})

    return JSONResponse({"saved": [s["path"] for s in saved], "errors": errors})


def _file_preview(dest: Path, data: bytes, max_chars: int = 1200) -> str:
    """Best-effort text preview for an imported file (empty for binaries)."""
    text_exts = {
        ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml",
        ".yml", ".toml", ".ini", ".cfg", ".csv", ".log", ".html", ".htm",
        ".css", ".scss", ".xml", ".gd", ".sh", ".ps1", ".bat", ".env",
    }
    if dest.suffix.lower() not in text_exts:
        return ""
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    if not text.strip():
        return ""
    return text[:max_chars]


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _running_future, _active_workers, _lock
    # If the server is exposed beyond localhost, require the token. Bound to
    # 127.0.0.1 (the default), the OS already keeps LAN clients out, so we
    # skip the check to keep the localhost flow frictionless.
    host = load_config().get("ui", {}).get("host", "127.0.0.1")
    if host in ("0.0.0.0", "::", ""):
        raw = ws.query_params.get("token", "")
        token = raw[0] if isinstance(raw, list) and raw else raw
        if token != _get_web_token():
            await ws.close(code=4401, reason="Unauthorized")
            return
    await ws.accept()
    _clients.append(ws)

    memory = Memory()
    await ws.send_text(json.dumps({"type": "state",
        "routines": _load_routines(),
        "notes": _load_notes(),
        "remembered": _load_remembered(),
    }))
    await ws.send_text(json.dumps({"type": "effort", "tier": _get_effort_tier()}))
    await ws.send_text(json.dumps({"type": "lang", "lang": "en", "name": "English"}))
    await ws.send_text(json.dumps({"type": "mute", "muted": is_muted()}))
    await ws.send_text(json.dumps({"type": "schedule", "events": schedule_list_events()}))
    # Tell the UI which provider/model is currently active so the buttons light up on load.
    ctx = load_config().get("brain", {})
    await ws.send_text(json.dumps({
        "type": "provider",
        "name": ctx.get("active_provider", ""),
        "model": ctx.get("active_provider", ""),
        "label": get_providers().get(ctx.get("active_provider", ""), {}).get("label", ""),
        "current": True,
    }))
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
                    await ws.send_text(json.dumps({"type": "status", "text": "connected"}))
                    continue

                # Brand-new user request: newest message wins, so hard-stop
                # any in-flight thinking or speaking. abort_all() sets the
                # sticky abort flag, which the old worker's finally clears
                # once it fully unwinds.
                abort_all()

                result_holder = {}
                done_event = asyncio.Event()

                def _run_request():
                    global _active_workers
                    reset_abort()
                    try:
                        result_holder["value"] = process_request(text)
                    except Aborted:
                        result_holder["value"] = None
                    finally:
                        with _lock:
                            _active_workers -= 1
                        reset_abort()
                        ws_loop.call_soon_threadsafe(done_event.set)

                ws_loop = asyncio.get_running_loop()
                with _lock:
                    _active_workers += 1
                threading.Thread(target=_run_request, daemon=True).start()
                await done_event.wait()
                response = result_holder.get("value")
                with _lock:
                    _running_future = None
                if response:
                    # Newest message wins: interrupt any current speech, then speak.
                    threading.Thread(target=interrupt_and_speak, args=(response,), daemon=True).start()
                else:
                    await ws.send_text(json.dumps({"type": "status", "text": "connected"}))

            elif msg_type == "wake":
                await ws.send_text(json.dumps({"type": "status", "text": "listening"}))
                def _run_mic_pipeline():
                    try:
                        handle_wake()
                    except Exception as e:
                        print(f"[Mic] Error: {e}")
                threading.Thread(target=_run_mic_pipeline, daemon=True).start()

            elif msg_type == "stop":
                # Stop talking AND thinking: set the sticky abort flag, cancel
                # the in-flight worker, and cut any audio. The abort flag stays
                # SET until the running worker fully unwinds (its own finally
                # clears it), so a half-finished request can never keep going
                # or speak afterward.
                with _lock:
                    fut = _running_future
                    if fut is not None and not fut.done():
                        fut.cancel()
                    _running_future = None
                abort_all()
                # If there is no worker in flight, nobody will clear the abort
                # flag for us — re-arm now so the next request isn't stuck.
                with _lock:
                    if _active_workers == 0:
                        reset_abort()
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

            elif msg_type == "switch_model":
                # Explicit model switching between DeepSeek / Kimi / Groq.
                key = msg.get("model", "") or msg.get("provider", "")
                if not key:
                    await ws.send_text(json.dumps({"type": "model_msg", "text": "No model specified."}))
                    continue
                if set_active_provider(key):
                    label = get_providers().get(key, {}).get("label", key)
                    from brain.events import broadcast
                    broadcast({
                        "type": "provider_changed",
                        "provider": key,
                        "label": label,
                        "model": get_providers().get(key, {}).get("model", key),
                    })
                    await ws.send_text(json.dumps({
                        "type": "provider",
                        "name": key,
                        "label": label,
                        "model": get_providers().get(key, {}).get("model", key),
                        "current": True,
                    }))
                    await ws.send_text(json.dumps({
                        "type": "model_msg",
                        "text": f"Model switched to {label}.",
                    }))
                else:
                    await ws.send_text(json.dumps({"type": "model_msg", "text": f"Unknown model '{key}'."}))

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


def start_web_background(port: int = 8765, host: str = "127.0.0.1") -> None:
    if host in ("0.0.0.0", "::"):
        print(f"[WARN] UI bound to {host}:{port} — LAN clients must present the "
              f"WS token (served to loopback only via /api/token).")
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
