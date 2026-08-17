"""Lydia — voice AI assistant for Windows. API-only brain, voice, tools, memory."""
from __future__ import annotations
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from brain.config import load_config, set_active_provider, get_active_provider, get_providers
from brain.context import ContextManager
from brain.events import broadcast
from brain.llm import chat_with_tools
from brain.memory import Memory
from brain.stt import record_until_silence, transcribe_audio, set_abort_event
from brain.tts import speak, speak_streamed, is_speaking, stop_speaking
from brain.tools.router import TOOL_SCHEMAS, dispatch
from brain.wake import listen_for_wake_word

_MAX_TOOL_LOOPS = 15
_MEMORY_DIR = Path(__file__).parent.parent / "memory_data"

_abort = threading.Event()
set_abort_event(_abort)
_muted = threading.Event()

_context = ContextManager()
_memory = Memory()


class Aborted(Exception):
    pass


def abort_all() -> None:
    """Force-stop talking / thinking right now.

    Sets the abort flag so any in-flight generation is interrupted,
    kills whatever is being spoken, and tells the UI we're idle again.
    The flag stays SET until the running worker actually stops, so a
    background request can't keep going (or speak) after a Stop.
    """
    _abort.set()
    stop_speaking()
    broadcast({"type": "status", "message": "Stopped."})


def reset_abort() -> None:
    """Re-arm for a fresh request after a stop/abort.

    Only the worker that owns the cancelled request should clear the
    flag once it has fully unwound. This guarantees a fired Stop never
    leaves a half-finished response that keeps talking anyway.
    """
    _abort.clear()


def is_stop_command(text: str) -> bool:
    cleaned = text.strip().lower().rstrip(".,!?")
    return cleaned in {"stop", "cancel", "abort", "shut up", "be quiet", "nevermind"}


def _check_abort() -> None:
    if _abort.is_set():
        raise Aborted()


def is_muted() -> bool:
    return _muted.is_set()


def toggle_mute() -> None:
    if _muted.is_set():
        _muted.clear()
        broadcast({"type": "mute", "muted": False})
    else:
        _muted.set()
        stop_speaking()
        broadcast({"type": "mute", "muted": True})


def speak_if_unmuted(text: str) -> None:
    if not _muted.is_set():
        speak(text)


def speak_streamed_if_unmuted(text: str) -> None:
    if not _muted.is_set():
        speak_streamed(text)


def interrupt_and_speak(text: str) -> None:
    """Mute-gated speech that ALWAYS cuts off any in-progress audio
    before speaking the new message. Newest message wins."""
    if _muted.is_set():
        return
    # Cancel whatever is currently being spoken so the new message takes over.
    stop_speaking()
    speak_streamed(text)


def _play_beep() -> None:
    try:
        t = np.linspace(0, 0.12, int(24000 * 0.12), endpoint=False)
        tone = 0.3 * np.sin(2 * np.pi * 600 * t).astype(np.float32)
        sd.play(tone, samplerate=24000)
        sd.wait()
    except Exception:
        pass


def _load_legacy_facts_text() -> str:
    facts = _memory.load_legacy_facts()
    if facts:
        return "## Your Memory\n" + "\n".join(facts)
    return ""


def _load_routines_text() -> str:
    routines = _memory.load_routines()
    if not routines:
        return ""
    lines = ["## Learned Routines"]
    for r in routines:
        lines.append(f"- When user says \"{r.get('trigger', '')}\": {r.get('steps', '')}")
    return "\n".join(lines)


def _system_prompt() -> str:
    now = datetime.now().strftime("%A, %B %d %Y, %I:%M %p")
    cfg = load_config()
    personality = cfg.get("lydia", {}).get(
        "personality",
        "You are Lydia, a capable coding assistant and work partner.",
    )
    old_facts = _load_legacy_facts_text()
    old_routines = _load_routines_text()

    lang = os.environ.get("LYDIA_LANG", "en")
    lang_instruction = "Always reply in Mandarin Chinese (中文)." if lang == "zh" else "Reply in English."

    prompt = f"""{personality}

{lang_instruction}

## Your Capabilities
- See the screen, click, type, scroll, take screenshots.
- Open apps, URLs, control media, manage windows.
- Web search, file read/write, run Python/shell, clipboard, system controls.
- Coding: read project tree, grep code, edit files, run tests/linters.
- Spotify, Discord, Tebex integrations.

## Tool-Using Rules
- JUST DO IT. Don't ask permission for safe actions.
- For destructive ops (kill process, shutdown, delete files), confirm once.
- For UI tasks: focus_window → read_screen/find_on_screen → click_at → verify.
- For coding tasks: read_project/read_file/grep_project first, then edit_file, then verify with tests/linter.
- Chain up to {_MAX_TOOL_LOOPS} tool calls. After edits, verify.

{old_facts}

{old_routines}

Current time: {now}. Answer concisely unless more detail is needed."""
    return prompt.strip()


def _execute_tool(name: str, args: dict) -> str:
    result = dispatch(name, args)
    if result.startswith("Tool '") and "failed:" in result:
        time.sleep(0.5)
        result = dispatch(name, args)
    return result


def process_request(user_text: str) -> str:
    """Process a user message and return the assistant's text response."""
    _check_abort()
    # Newest message wins: immediately cut any audio still being spoken
    # so we never keep talking over a brand-new request.
    stop_speaking()
    _play_beep()
    broadcast({"type": "user", "text": user_text})
    broadcast({"type": "status", "message": "Thinking..."})

    facts = _memory.search_facts(user_text)
    messages = _context.get_messages()
    if facts:
        messages = [{"role": "system", "content": "Relevant context: " + "; ".join(facts)}] + messages
    messages.append({"role": "user", "content": user_text})
    full_messages = [{"role": "system", "content": _system_prompt()}] + messages

    try:
        response_text = chat_with_tools(
            messages=full_messages,
            tool_schemas=TOOL_SCHEMAS,
            execute_tool=_execute_tool,
            max_loops=_MAX_TOOL_LOOPS,
            abort_check=_check_abort,
            on_tool_call=lambda name, args: broadcast({"type": "tool", "name": name, "args": args}),
            on_tool_result=lambda name, result: broadcast({"type": "tool_result", "name": name, "result": result[:200]}),
            on_progress=lambda: speak_if_unmuted("Working on it."),
        )
    except Aborted:
        raise
    except Exception as e:
        print(f"[WARN] LLM call failed: {e}")
        response_text = f"Oops, my brain's having a moment — try again?"

    _context.add("user", user_text)
    _context.add("assistant", response_text)
    _memory.extract_and_store_facts(response_text, user_text)

    broadcast({"type": "response", "text": response_text})
    return response_text


def handle_wake() -> None:
    _abort.clear()
    try:
        _handle_wake_inner()
    except Aborted:
        pass
    except Exception as e:
        import traceback
        print(f"[ERROR] {e}")
        traceback.print_exc()
        if not _abort.is_set():
            speak_if_unmuted("Sorry, something went wrong.")
    finally:
        _abort.clear()
        from brain.wake import consume_pending_wake
        if consume_pending_wake():
            time.sleep(0.4)
            handle_wake()
        else:
            broadcast({"type": "status", "message": "Ready."})


def _handle_wake_inner() -> None:
    if is_speaking():
        stop_speaking()
        broadcast({"type": "status", "message": "Ready."})
        return
    broadcast({"type": "status", "message": "Wake."})
    speak_if_unmuted("Yes?")

    broadcast({"type": "status", "message": "Listening..."})
    from brain.wake import pause_wake_mic, resume_wake_mic
    pause_wake_mic()
    time.sleep(0.15)
    try:
        audio = record_until_silence()
    finally:
        resume_wake_mic()
    _check_abort()

    if len(audio) / 16000 < 0.5:
        speak_if_unmuted("Didn't quite catch that — go ahead?")
        return

    user_text = transcribe_audio(audio)
    if not user_text.strip():
        speak_if_unmuted("Didn't quite catch that — go ahead?")
        return

    if is_stop_command(user_text):
        abort_all()
        raise Aborted()

    response_text = process_request(user_text)
    _check_abort()
    broadcast({"type": "status", "message": "Speaking..."})
    speak_streamed_if_unmuted(response_text)


def _keyboard_listener() -> None:
    try:
        import msvcrt
    except ImportError:
        return
    while True:
        try:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':
                    abort_all()
                elif key in (b'\x00', b'\xe0'):
                    special = msvcrt.getch()
                    if special == b'<':
                        cmd = input("\n[Type your command] ")
                        if cmd.strip():
                            _handle_typed_command(cmd.strip())
                    elif special == b'R':
                        toggle_mute()
            time.sleep(0.05)
        except Exception:
            time.sleep(0.1)


def _handle_typed_command(text: str) -> None:
    _abort.clear()
    try:
        response = process_request(text)
        interrupt_and_speak(response)
    except Aborted:
        pass
    finally:
        _abort.clear()


def main() -> None:
    import webbrowser
    from brain.web import start_web_background
    from brain.discord_bot import start_discord_bot

    cfg = load_config()
    host = cfg.get("ui", {}).get("host", "0.0.0.0")
    port = cfg.get("ui", {}).get("port", 8765)

    print("=" * 50)
    print("  Lydia — Voice AI Assistant")
    print("=" * 50)
    print(f"  UI: http://localhost:{port}")
    print("  Keys: Esc = stop | F2 = type | Insert = mute")
    print("=" * 50)

    start_web_background(port=port, host=host)
    start_discord_bot()
    threading.Thread(target=_keyboard_listener, daemon=True).start()

    if not os.environ.get("LYDIA_OPEN_UI") == "0":
        webbrowser.open(f"http://localhost:{port}")

    speak_if_unmuted("Lydia online.")
    listen_for_wake_word(handle_wake)


if __name__ == "__main__":
    main()
