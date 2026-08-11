"""Text-to-speech using cloud APIs (Edge TTS default, Groq PlayAI optional)."""
from __future__ import annotations
import asyncio
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import edge_tts
import numpy as np
import requests
import sounddevice as sd

from brain.config import load_config


_SPEAKING = threading.Event()
_INTERRUPT = threading.Event()


def is_speaking() -> bool:
    return _SPEAKING.is_set()


def stop_speaking() -> None:
    _INTERRUPT.set()
    sd.stop()
    _SPEAKING.clear()


def _pcm_from_mp3(path: str) -> np.ndarray | None:
    """Decode an MP3 file to a normalized float32 numpy array using ffmpeg."""
    if not shutil.which("ffmpeg"):
        return None
    wav_path = path.replace(".mp3", ".wav")
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ar", "24000", "-ac", "1", wav_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        with wave.open(wav_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
        return samples
    except Exception:
        return None
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except Exception:
            pass


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _wait_or_interrupt() -> bool:
    while sd.get_stream() and sd.get_stream().active:
        if _INTERRUPT.is_set():
            sd.stop()
            return True
        _INTERRUPT.wait(0.05)
    return _INTERRUPT.is_set()


async def _edge_tts_to_file(text: str, path: str, voice: str, speed: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate=speed)
    await communicate.save(path)


def _speak_file(path: str) -> None:
    audio = _pcm_from_mp3(path)
    if audio is None:
        return
    _SPEAKING.set()
    sd.play(audio, samplerate=24000)
    _wait_or_interrupt()
    _SPEAKING.clear()


def speak(text: str) -> None:
    """Speak text aloud. Interruptible via stop_speaking()."""
    _INTERRUPT.clear()
    cfg = load_config().get("tts", {})
    provider = cfg.get("provider", "edge")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        out_path = f.name

    try:
        if provider == "edge":
            asyncio.run(_edge_tts_to_file(
                text, out_path,
                cfg.get("voice", "en-US-AriaNeural"),
                cfg.get("speed", "+0%"),
            ))
        elif provider == "groq":
            _speak_groq(text, out_path, cfg)
        else:
            return
        _speak_file(out_path)
    finally:
        _INTERRUPT.clear()
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass


def speak_streamed(text: str) -> None:
    """Speak text sentence by sentence for lower latency."""
    sentences = _split_sentences(text)
    if not sentences:
        return
    if len(sentences) == 1:
        speak(text)
        return

    _INTERRUPT.clear()
    _SPEAKING.set()
    try:
        for sentence in sentences:
            if _INTERRUPT.is_set():
                break
            speak(sentence)
            if _INTERRUPT.is_set():
                break
    finally:
        _SPEAKING.clear()
        _INTERRUPT.clear()


def _speak_groq(text: str, out_path: str, cfg: dict) -> None:
    env = {}
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    api_key = env.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set for TTS")

    model = cfg.get("model", "playai-tts")
    voice = cfg.get("voice", "Celeste-PlayAI")
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "voice": voice, "input": text, "response_format": "mp3"},
        timeout=30,
    )
    if r.status_code == 200:
        Path(out_path).write_bytes(r.content)
    else:
        raise RuntimeError(f"Groq TTS error {r.status_code}: {r.text}")
