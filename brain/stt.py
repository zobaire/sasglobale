"""Speech-to-text using cloud APIs (Groq Whisper)."""
from __future__ import annotations
import tempfile
import wave
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd

from brain.config import load_config, load_dotenv


_ABORT_EVENT = None


def set_abort_event(event) -> None:
    """Register an optional threading.Event to interrupt recording."""
    global _ABORT_EVENT
    _ABORT_EVENT = event


def _save_wav(audio: np.ndarray, path: str, sample_rate: int = 16000) -> None:
    """Save a float32 mono numpy array as a 16-bit WAV file."""
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def record_until_silence(
    sample_rate: int = 16000,
    silence_threshold: float = 0.012,
    max_seconds: int = 30,
) -> np.ndarray:
    """Record microphone audio until silence is detected.

    Returns a float32 mono numpy array at sample_rate.
    """
    chunk = int(sample_rate * 0.3)
    recording = []
    silent_chunks = 0
    silent_chunks_needed = 7
    heard_speech = False
    speech_threshold = 0.015

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32") as stream:
        while True:
            if _ABORT_EVENT and _ABORT_EVENT.is_set():
                print("[STT] Recording aborted.")
                break

            data, _ = stream.read(chunk)
            flat = data.flatten()
            recording.append(flat)
            rms = float(np.sqrt(np.mean(flat ** 2)))

            if rms >= speech_threshold:
                heard_speech = True
                silent_chunks = 0
            elif heard_speech and rms < silence_threshold:
                silent_chunks += 1

            if heard_speech and silent_chunks >= silent_chunks_needed:
                print("[STT] Silence detected, stopping recording.")
                break
            if len(recording) * chunk >= max_seconds * sample_rate:
                print(f"[STT] Max recording time reached ({max_seconds}s)")
                break

    if not recording:
        return np.zeros(chunk, dtype=np.float32)
    return np.concatenate(recording)


def transcribe_audio(audio: np.ndarray, language: str | None = None) -> str:
    """Transcribe audio using the configured cloud STT provider."""
    import os
    if language is None:
        language = os.environ.get("LYDIA_LANG", "en")
    cfg = load_config().get("stt", {})
    provider = cfg.get("provider", "groq")

    if provider == "groq":
        return _transcribe_groq(audio, cfg.get("model", "whisper-large-v3-turbo"), language)

    return f"[STT error: unknown provider '{provider}']"


def _transcribe_groq(audio: np.ndarray, model: str, language: str) -> str:
    api_key = load_dotenv().get("GROQ_API_KEY", "")
    if not api_key:
        return "[STT error: GROQ_API_KEY not set in .env]"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name

    try:
        _save_wav(audio, wav_path)
        with open(wav_path, "rb") as wav:
            files = {"file": ("audio.wav", wav, "audio/wav")}
            data = {"model": model, "language": language, "response_format": "json"}
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
                timeout=30,
            )
        if r.status_code == 200:
            return r.json().get("text", "").strip()
        return f"[STT error {r.status_code}: {r.text}]"
    except Exception as e:
        return f"[STT error: {e}]"
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except Exception:
            pass
