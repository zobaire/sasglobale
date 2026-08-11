# Lydia — Codebase Reference for Future AIs

> Last updated: 2026-07-31 by Kimi Code CLI
> Purpose: Onboard future me / other AI agents onto Lydia's architecture, configuration, and extension points.

---

## 1. What Lydia Is

Lydia is a Windows-native voice AI assistant / coding partner. She runs as a Python desktop app with:

- **Voice activation**: wake-word → listen → STT → LLM tool loop → TTS reply
- **Desktop control**: screenshots, OCR, mouse/keyboard, window focus, app launching
- **Web access**: DuckDuckGo search, page fetch, weather
- **Integrations**: Spotify, Discord server stats, Tebex store sales
- **Memory**: SQLite summaries + ChromaDB semantic facts + `notes.md` + routines
- **UI**: FastAPI WebSocket server serving a 3D HUD at `http://localhost:8765`

The active UI is `ui/index.html` (amber cyberpunk graph HUD). The old `lydia/` package has been replaced by `brain/`.

---

## 2. Directory Layout

```
C:/Users/book/Desktop/Lydia
├── brain/                  # Python package (new brain)
│   ├── __init__.py         # empty
│   ├── main.py             # entry point, LLM loop, voice pipeline
│   ├── web.py              # FastAPI + WebSocket server, UI bridge
│   ├── config.py           # config loader/manager
│   ├── llm.py              # OpenAI-compatible LLM client + tool loop
│   ├── context.py          # rolling conversation window + auto-summarization
│   ├── memory.py           # ChromaDB facts + SQLite conversation summaries
│   ├── events.py           # internal event bus
│   ├── stt.py              # Groq Whisper cloud STT + silence recording
│   ├── tts.py              # Edge TTS / Groq PlayAI cloud TTS
│   ├── wake.py             # optional openWakeWord wake-word listener
│   └── tools/              # tool implementations routed to the LLM
│       ├── router.py       # TOOL_MAP + TOOL_SCHEMAS + dispatch()
│       ├── api_tools.py    # Spotify, Discord, Tebex
│       ├── app_control.py  # open_app, open_url, kill_process
│       ├── code_exec.py    # run_python sandbox
│       ├── desktop.py      # pyautogui, OCR, screenshots
│       ├── file_ops.py     # read/write/list/patch (path-allowlist gated)
│       ├── project.py      # coding brain: grep, symbols, tests, lint, edit
│       └── system.py       # volume, clipboard, brightness, lock, power, timers
├── ui/                     # active web UI
│   ├── index.html          # 3D ForceGraph HUD (current)
│   ├── indexV2.html        # alternate / future UI
│   └── vendor/             # 3d-force-graph.min.js
├── memory_data/            # runtime state + memory
│   ├── memory.db           # SQLite conversation summaries
│   ├── chroma/             # ChromaDB persistent embeddings
│   ├── routines/*.json     # learned trigger→steps routines
│   ├── notes.md            # free-form memory
│   ├── facts.json          # legacy facts (still loaded into prompt)
│   ├── effort.json         # persisted effort tier
│   ├── store_state.json    # last Tebex payment id
│   └── spotify_token.json  # OAuth refresh token
├── config.yaml             # single source of truth for providers, STT/TTS, etc.
├── .env                    # secrets (API keys, tokens)
├── .env.example            # template
├── requirements.txt        # pip deps
├── run.bat / stop.bat      # launcher scripts
└── bin/luacheck.exe        # external binary
```

---

## 3. Entry Point & Runtime Flow

```
python -m brain.main
```

`brain/main.py:main()`:
1. Starts FastAPI in a daemon thread (`lydia/web.py:start_web_background()`)
2. Opens browser to `http://localhost:8765`
3. Starts keyboard listener (`F2` type, `Esc` stop, `Insert` mute)
4. Enters `listen_for_wake_word(handle_wake)` — blocks forever

When wake word fires:

```
listen_for_wake_word()
  → handle_wake()                     # brain/main.py
    → _handle_wake_inner()
      → pause wake mic
      → record_until_silence()        # brain/stt.py
      → transcribe_audio()            # brain/stt.py (Groq Whisper)
      → process_request(user_text)    # brain/main.py
        → memory.search_facts(query)
        → context.get_messages()
        → _system_prompt()
        → chat_with_tools()           # brain/llm.py
          → dispatch(tool_name, args) # brain/tools/router.py
        → context.add()
        → memory.extract_and_store_facts()
        → speak_streamed(response)    # brain/tts.py
```

Barge-in: if wake word fires while busy, `abort_all()` is called — stops TTS, sets abort event, raises `Aborted` inside the pipeline.

---

## 4. Configuration

`config.yaml` is the single source of truth:

```yaml
lydia:
  name: Lydia
  personality: >
    You are Lydia, a cheerful, upbeat, and encouraging coding assistant...

brain:
  active_provider: deepseek
  temperature: 1.0
  max_tool_loops: 15

providers:
  deepseek: { type: openai, label: DeepSeek, model: deepseek-chat, base_url: https://api.deepseek.com/v1,   api_key: ... }
  kimi:     { type: openai, label: Kimi,     model: kimi-k3,         base_url: https://api.moonshot.cn/v1,    api_key: ... }
  groq:     { type: openai, label: Groq,     model: llama-3.3-70b-versatile, base_url: https://api.groq.com/openai/v1, api_key: ... }

context:  { max_messages: 24, summarize_after: 16 }
memory:   { db_path: memory_data/memory.db, chroma_path: memory_data/chroma, top_k: 3 }
stt:      { provider: groq, model: whisper-large-v3-turbo }
tts:      { provider: edge, voice: en-US-AriaNeural, speed: +0% }
wake_word:
  enabled: true
  backend: porcupine
  keyword_path: "Hey-Lydia_windows.ppn"   # train at console.picovoice.ai
  access_key: ""
  model: hey_jarvis                        # openWakeWord fallback
  chunk_size: 1280
  threshold: 0.5
ui:       { host: 0.0.0.0, port: 8765 }
tools:
  web_search:    { max_results: 5 }
  code_exec:     { timeout: 30 }
  allowed_paths: [~/Documents, ~/Desktop]
```

`brain/config.py` reads and writes this file. `brain/main.py` uses `set_active_provider()` for switching.

### Secrets
Provider API keys can live in `config.yaml` **or** `.env`. `brain/config.py` overlays keys from `.env` on top of `config.yaml`, so `.env` takes precedence.

Expected `.env` variables:
- `DEEPSEEK_API_KEY`, `KIMI_API_KEY`, `GROQ_API_KEY` — provider keys
- `GROQ_API_KEY` — also used for STT and optional Groq TTS
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `TEBEX_SECRET` — integrations

Run diagnostics to verify which providers are reachable:
```
python -m brain.diagnose
```

---

## 5. LLM Brain

`brain/main.py` orchestrates; `brain/llm.py:chat_with_tools()` implements the tool loop:

- OpenAI-compatible APIs only (DeepSeek, Kimi, Groq)
- Max tool loops from `config.yaml` (`brain.max_tool_loops`)
- Tools passed via the provider's native `tools` parameter
- Results appended as `role: tool` messages
- Retry once on tool failure
- No local models / no Ollama

System prompt (`_system_prompt()` in `brain/main.py`) injects:
- Configured personality from `lydia.personality`
- Current time
- Old facts from `facts.json` + `notes.md`
- Learned routines from `memory_data/routines/*.json`

### Context Management
`brain/context.py` keeps a rolling `deque(maxlen=max_messages)`. When it hits `summarize_after`, oldest half is summarized via `brain/llm.py:simple_chat()` and replaced with a system summary.

### Memory
`brain/memory.py`:
- **ChromaDB** collection `facts` for semantic fact retrieval (`top_k=3`)
- **SQLite** table `summaries` for conversation summaries
- `extract_and_store_facts()` triggers on keyword-heavy user messages and stores the raw user sentence

---

## 6. Tools

All tool schemas live in `brain/tools/router.py:TOOL_SCHEMAS`. The dispatch map is `TOOL_MAP`.

| Category | Tools |
|----------|-------|
| Web | `web_search`, `fetch_page`, `open_url`, `get_weather` |
| Apps | `open_app`, `kill_process` |
| Desktop vision | `read_screen` (OCR), `find_on_screen`, `screenshot` |
| Desktop mouse/keyboard | `click_at`, `move_mouse`, `scroll_screen`, `type_text`, `press_key`, `focus_window`, `get_open_windows`, `media_control` |
| Files | `read_file`, `write_file`, `list_files`, `apply_patch` — gated by `config.yaml` `tools.allowed_paths` |
| Code | `run_python` — subprocess sandbox, timeout from config |
| Coding brain | `read_project`, `grep_project`, `read_symbols`, `run_shell`, `run_tests`, `run_linter`, `edit_file` |
| Clipboard | `get_clipboard`, `set_clipboard` |
| System | `set_volume`, `get_volume`, `get_system_info`, `set_brightness`, `lock_screen`, `power_command`, `show_notification`, `set_timer` |
| Integrations | `spotify_control`, `discord_check`, `tebex_check`, `check_business` |

### Notable Implementation Details
- `desktop.py` uses **Windows.Media.Ocr** via PowerShell for OCR
- `app_control.py` has hard-coded Windows paths; Discord requires `--processStart Discord.exe`
- `file_ops.py` checks an allowlist defined in `config.yaml`
- `code_exec.py` writes a temp `.py` file and runs it with `sys.executable`
- `project.py` respects `.gitignore` when scanning the repo
- `system.py` uses C# COM interop via PowerShell for volume control

---

## 7. Web UI

`brain/web.py` runs FastAPI on `0.0.0.0:8765`:

- `GET /` → serves `ui/index.html`
- `/vendor/*` → static files from `ui/vendor/`
- `GET /api/battery` → returns cached DeepSeek / Kimi / Groq balance/rate-limit info
- `WS /ws` → main bidirectional channel (also receives live battery updates every 30s)

Battery polling is handled by `brain/battery.py`:
- DeepSeek: account balance from `api.deepseek.com/user/balance`
- Kimi: account balance from Moonshot `/users/me/balance`
- Groq: rate-limit headers from a minimal chat completion call

### WebSocket Events (Backend → Frontend)

| Event | Fields | Meaning |
|-------|--------|---------|
| `state` | `routines`, `notes` | Initial memory graph data |
| `effort` | `tier` | Current effort tier |
| `lang` | `lang`, `name` | Current STT language |
| `user` | `text` | User transcript |
| `assistant` | `text` | Assistant reply |
| `status` | `text` | `connected/listening/thinking/talking` |
| `tool` | `name`, `args` | Tool call start |
| `tool_result` | `name`, `text` | Tool result |
| `mute` | `muted` | Mute state |
| `listen` | `listening` | Wake-mic enabled state |
| `provider` | `name` | Active provider changed |
| `battery` | `groq`, `deepseek`, `kimi` | Balance/rate-limit update |

### WebSocket Commands (Frontend → Backend)

| Command | Fields | Action |
|---------|--------|--------|
| `user_text` | `text` | Type a command |
| `wake` | — | Push-to-talk mic pipeline |
| `stop` | — | Abort all |
| `set_lang` | `lang` | Toggle `en`/`zh` |
| `set_effort` | `tier` | `snappy`/`balanced`/`max`/`ultra` → maps to provider |
| `set_mute` | `muted` | Toggle mute |
| `set_listen` | `listening` | Enable/disable wake mic |

### UI Files
- `ui/index.html` — current active HUD. 3D ForceGraph of Lydia + Routines + Memory nodes, status dial, chat panel, effort selector, provider battery meters.
- `ui/indexV2.html` — alternate / future UI experiment.

---

## 8. Audio Pipeline

### STT (`brain/stt.py`)
- Uses **Groq Whisper API** (`whisper-large-v3-turbo` by default)
- Records from mic in 300 ms chunks until ~2.1 s of silence or 30 s max
- Abort event checked every chunk
- Language is configurable but defaults to English

### TTS (`brain/tts.py`)
- Default: **Edge TTS** (free, cloud, no API key)
- Optional: **Groq PlayAI TTS** (requires `GROQ_API_KEY` and accepting terms)
- Decodes MP3 to PCM with `ffmpeg` (must be installed and on PATH)
- `speak_streamed()` splits by sentence and plays as generated
- `stop_speaking()` interrupts playback immediately via `sounddevice.stop()`

### Wake Word (`brain/wake.py`)
- Primary: **Porcupine** with a custom keyword (intended: "Hey Lydia")
- Fallback: `openwakeword` with `hey_jarvis`
- Final fallback: push-to-talk console loop
- 16 kHz, 1280-sample chunks
- Pauses mic when STT is recording (`pause_wake_mic` / `resume_wake_mic`)
- Barge-in: second wake while busy calls `abort_all()`
- 2 s cooldown after normal wake to avoid re-triggering on "Yes?"

To enable "Hey Lydia":
1. Sign up at https://console.picovoice.ai
2. Train a custom wake word "Hey Lydia" for Windows
3. Download the `.ppn` file into the project root
4. Set `wake_word.keyword_path` in `config.yaml` (or `WAKE_KEYWORD_PATH` in `.env`)
5. Set `PICOVOICE_ACCESS_KEY` in `.env`

---

## 9. Keyboard Shortcuts

Implemented in `brain/main.py:_keyboard_listener()`:

| Key | Action |
|-----|--------|
| `Esc` | Abort all / stop |
| `F2` | Type a command |
| `Insert` | Toggle mute |

---

## 10. Dependencies

`requirements.txt`:

```
openai>=1.40.0
fastapi>=0.110
uvicorn[standard]>=0.29
python-dotenv>=1.0
requests>=2.31
websockets>=12
numpy>=1.26
sounddevice>=0.4.6
edge-tts>=6.1
pyautogui>=0.9.54
chromadb>=0.5.0
sqlalchemy>=2.0
pyyaml>=6.0
pillow>=10.0
mss>=9.0
ddgs>=3.0
# Optional wake word deps
# openwakeword>=0.6.0
# pyaudio>=0.2.13
```

External requirements:
- `ffmpeg` must be installed and on PATH for TTS MP3 decoding.
- Windows PowerShell for OCR, volume, clipboard, and system controls.

---

## 11. Known Issues & Technical Debt

1. **Secrets in config**: API keys are stored in `config.yaml` in plain text. Consider moving them to `.env` and reading via `python-dotenv`.
2. **STT language**: `stt.py` accepts a language parameter but the UI toggle sets `LYDIA_LANG`, which is not yet wired to transcription.
3. **No vision model integration**: Screenshots use Windows OCR only. No image is sent to an LLM vision model.
4. **No deep-thought streaming**: UI has `thought`/`thought_delta` handlers, but backend never emits them.
5. **Destructive ops**: confirmation is left to the LLM system prompt — no code-level gate.
6. **Wake word model**: default is `hey_jarvis`; switch to a custom model/trigger if desired.
7. **Windows-only**: heavy PowerShell/COM interop makes portability hard.
8. **TTS requires ffmpeg**: Edge TTS outputs MP3; playback requires ffmpeg on PATH.

---

## 12. New Brain Features

Lydia has been rebuilt into the `brain/` package with a coding-first architecture:

- **API-only providers**: DeepSeek, Kimi, Groq. No local Ollama dependency.
- **Cloud STT/TTS**: Groq Whisper for speech-to-text; Edge TTS (or Groq PlayAI) for text-to-speech.
- **Coding tools**: `read_project`, `grep_project`, `read_symbols`, `run_shell`, `run_tests`, `run_linter`, `edit_file`.
- **Safe editing**: `apply_patch` uses SEARCH/REPLACE blocks.
- **Project awareness**: `read_project` and `grep_project` respect `.gitignore`.
- **Configurable personality**: `lydia.personality` in `config.yaml`.

### 12.1 Brain Architecture (Implemented)

```
┌─────────────────────────────────────────┐
│  UI Layer (FastAPI + WebSocket)          │
│  - 3D graph HUD                          │
│  - chat / thoughts panels                │
│  - provider battery meters               │
├─────────────────────────────────────────┤
│  Brain Orchestrator                      │
│  - process_request() drives the loop     │
│  - chat_with_tools() executes LLM calls  │
├─────────────────────────────────────────┤
│  Skill Registry (brain/tools/)           │
│  - Read project / grep / symbols         │
│  - Edit files with SEARCH/REPLACE patch  │
│  - Run tests / linters / shell           │
│  - Web, desktop, system, integrations    │
├─────────────────────────────────────────┤
│  Model Router                            │
│  - snappy  → Groq                       │
│  - balanced→ Kimi                       │
│  - max     → DeepSeek                   │
│  - ultra   → DeepSeek                   │
├─────────────────────────────────────────┤
│  Memory                                  │
│  - Semantic facts (ChromaDB)             │
│  - Conversation summaries (SQLite)       │
│  - Routines + notes.md                   │
└─────────────────────────────────────────┘
```

### 12.2 Recommended Next Steps

1. **Move secrets to `.env`**
   - Read provider API keys from `.env` instead of `config.yaml`
   - Use `python-dotenv` for consistent loading

2. **Vision Model**
   - Add a tool that sends screenshots to a vision-capable model
   - Use Groq or Kimi vision endpoints

3. **Reasoning Streaming**
   - Stream `<think>` blocks to the UI Thoughts panel
   - Requires provider that exposes reasoning tokens

4. **UI Improvements for Coding**
   - Add file-tree panel
   - Add diff/code preview with syntax highlighting
   - Add "Accept / Reject / Retry" buttons for edits
   - Add project selector

5. **Memory Upgrades**
   - Store project conventions ("we use tabs", "Vue not React")
   - Remember failed attempts and corrections
   - Long-term session summaries across restarts

### 12.3 Implemented Tools

```python
# Project introspection
read_project(root: str, depth: int) -> tree
grep_project(pattern: str, path: str, max_results: int) -> matches
read_symbols(file_path: str) -> functions/classes

# Safe editing
apply_patch(path: str, patch: str) -> result
edit_file(path: str, patch: str) -> result   # alias

# Verification
run_tests(path: str) -> result
run_linter(path: str) -> result
run_shell(command: str, timeout: int) -> result

# Still to add
# git_status() / git_diff() / git_commit()
# analyze_image(image_path_or_screenshot: str, prompt: str)
```

### 12.4 Files to Modify First

| File | Change |
|------|--------|
| `brain/tools/router.py` | Add new tool schemas + mappings |
| `brain/tools/git_ops.py` (new) | Git wrappers |
| `brain/tools/vision.py` (new) | Send images to vision model |
| `brain/main.py` | Emit thought events, per-task routing |
| `brain/web.py` | Add `/api/project`, `/api/file` REST endpoints for UI |
| `ui/index.html` | Add file tree, diff view, accept/reject buttons |

---

## 13. Quick Reference for AI Editors

### How to add a new tool
1. Implement function in the appropriate `brain/tools/*.py` file
2. Add entry to `TOOL_MAP` in `brain/tools/router.py`
3. Add schema to `TOOL_SCHEMAS` in same file
4. Keep it Windows-safe unless adding a cross-platform guard
5. Return a string — the LLM sees it as tool result

### How to add a new provider
1. Add entry under `providers` in `config.yaml`
2. Use `type: openai` for OpenAI-compatible APIs
3. Call `set_active_provider("key")` or change `brain.active_provider` manually

### How to change system prompt
Edit `lydia.personality` in `config.yaml`, or edit `_system_prompt()` in `brain/main.py`.

### How to test without voice
Use the web UI chat box or press `F2` in the terminal to type commands.

### How to restart cleanly
Kill the process; there is no graceful shutdown beyond `stop.bat`.

---

## 14. Glossary

| Term | Meaning |
|------|---------|
| `Aborted` | Internal exception raised when user hits stop / barge-in |
| `_abort` Event | Global flag checked by recording, LLM loop, TTS |
| `TOOL_SCHEMAS` | JSON schemas passed to LLM for function calling |
| `ContextManager` | Rolling chat history with summarization |
| `Memory` | ChromaDB + SQLite persistence layer |
| `openWakeWord` | On-device wake-word detection library |
| `Edge TTS` | Cloud text-to-speech from Microsoft Edge |
| `Groq Whisper` | Cloud speech-to-text from Groq |

---

*End of reference. When modifying this project, keep changes minimal, match existing naming (e.g. `brain/tools/*.py`), and update this doc if you change architecture or add major features.*
