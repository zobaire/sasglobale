# Lydia

Voice assistant / work partner for Windows. DeepSeek brain, Groq ears + eyes + voice, wake word with barge-in, 3-panel UI showing her thoughts and learned routines.

## Architecture

| Part | Tech |
|---|---|
| Brain | DeepSeek `deepseek-chat` (tool loop) + `deepseek-reasoner` (deep_think, reasoning streamed to Thoughts panel) |
| Ears | Porcupine wake word → Groq Whisper (`whisper-large-v3-turbo`) |
| Eyes | Screenshot → Groq vision (`llama-4-scout`) → description feeds the brain |
| Voice | Groq PlayAI TTS, chunked playback → interruptible (barge-in) |
| Hands | Tools: open_app, open_url, run_powershell (destructive ops gated), type_text, press_keys |
| Memory | `memory_data/notes.md` + `memory_data/routines/*.json`, live in UI |
| UI | 3 panels (conversation / thoughts / routines+memory), FastAPI + WebSocket, `ui/index.html` |

## Setup

1. **Python 3.10+**, then:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in:
   - `DEEPSEEK_API_KEY` — https://platform.deepseek.com
   - `GROQ_API_KEY` — https://console.groq.com (accept the PlayAI TTS terms once in the console, or TTS requests will be rejected)
   - `PICOVOICE_ACCESS_KEY` — https://console.picovoice.ai (free). Without it Lydia falls back to press-Enter-to-talk.
3. **Wake word "Lydia"**: in the Picovoice Console, train a custom keyword "Lydia" for Windows, download the `.ppn`, set `WAKE_KEYWORD_PATH` to its path. Until then the built-in word **"Jarvis"** is used.
4. Run:
   ```
   python -m lydia.main
   ```
5. Open http://localhost:8765

## Using her

- Say the wake word, wait for the beep, speak. ~1.2s of silence ends the command.
- **Barge-in**: say the wake word while she is talking — she stops immediately and listens.
- Type in the UI instead of speaking any time.
- "Look at my screen and explain this error" → screenshot → Groq vision.
- After a multi-step task she may offer to save it as a routine; saved routines appear in the right panel and run on their trigger phrase.
- Destructive PowerShell (delete/kill/shutdown) is blocked until you confirm out loud.

## Troubleshooting

- **TTS error 4xx**: accept PlayAI terms in the Groq console, or switch voice/model in `.env`.
- **Wake word never fires**: check mic default device; try the built-in "Jarvis" first (leave `WAKE_KEYWORD_PATH` empty).
- **Mic conflict in keyboard mode**: keyboard mode opens its own mic stream per recording; close other apps holding the mic exclusively.
- **She hears herself**: if TTS says her name through speakers she may barge-in on herself — use headphones or rename-trigger sensitivity later.
