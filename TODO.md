# Lydia Backend — Upgrade TODO (verified against current code 2026-08-19)

> Status legend: [ ] = open, [x] = done (verified in code)

## Already implemented (my earlier audit was wrong — these are in the code now)

- [x] **Safe tool retry** — `brain/main.py:_execute_tool` only retries read-only /
      idempotent tools (`_RETRYABLE_TOOLS`). `write_file`, `kill_process`,
      `power_command` etc. are NEVER auto-retried; the LLM sees the error and decides.
- [x] **Web server guard** — binds `127.0.0.1:8765` by default (config.yaml).
      If exposed via `0.0.0.0`, WS connections require a token fetched from the
      loopback-only `/api/token` endpoint. LAN randos can't drive tools.
- [x] **No error-summary injection** — `brain/context.py:_compress_oldest` drops the
      oldest half even on failure and refuses summaries starting with `[LLM error`.
- [x] **Secrets out of config.yaml** — `load_config()` overlays keys from `.env`;
      `save_config()` strips `api_key` before writing. Keys never persist to YAML.
- [x] **File upload end-to-end** — `/api/import` in `brain/web.py` + FormData POST
      wired in `ui/indexV2.html` (attach button → chat shows "📎 Attached" + saved/errors).
- [x] **Conversation persistence** — `ContextManager(initial_summaries=...)` replays
      the last 5 SQLite summaries into the prompt on boot.
- [x] **Config values used** — `max_tool_loops` and `brain.temperature` read from
      config.yaml by both `chat_with_tools` and `simple_chat`.
- [x] **Fact-extraction junk filter** — `memory.py` has `_FACT_JUNK_PATTERNS`
      ("i have a question", "i want to", "i need help"…), `_FACT_MIN_LENGTH`,
      and rejects questions. No more garbage facts.
- [x] **Env parsing dedupe** — `config.py:load_dotenv()` is the single source of
      truth; web.py imports it.
- [x] **Battery meters honest** — no fake 50% placeholders; returns `pct: None`
      ("—" in UI) until real telemetry exists.

## P0 — still genuinely open

(none — the three items I originally flagged are all already handled)

## P1 — High-impact upgrades (real gaps)

- [x] **Stream final responses** — `main.py` already emits `assistant_delta` +
      `thought_delta` over WS; added the missing `assistant_delta` handler in
      `ui/indexV2.html` so chat now renders tokens live and finalizes in place.
- [x] **Vision tool** — `brain/tools/vision.py` has `analyze_image(path, prompt)`
      (downscale → base64 JPEG → Kimi vision model), registered in router.py,
      `KIMI_API_KEY` present in .env. Use after `screenshot()` to truly "see".
- [ ] **UI polish** — composer is already wide (`min(1440px, 97vw)`), but consider
      a dedicated input row + "thinking" progress bar while waiting.

## P2 — Polish & DX

- [ ] **Tests** — pytest for context, memory, dispatch, schedule, config.
      `run_tests` currently finds nothing.
- [ ] **Logging** — replace `print()` with `logging` module + rotating file handler.
      Clean root clutter: `out.txt`, `backend_test.log`, `-p/`.
- [ ] **Git tools** — `git_status`, `git_diff`, `git_commit` for the coding brain
      (none exist today).
- [ ] **Project-convention memory** — remember per-project rules ("Fate's Pair uses
      GDScript 4, tabs not spaces") and inject them into the prompt.
- [ ] **Code-level destructive-op gate** — prompt says "confirm once" but nothing
      enforces it. Add a real confirm flow for `power_command` / `kill_process`.
- [ ] **Cache headers / CSP** on static UI assets + cache-buster bump after deploys.
- [ ] **Graceful shutdown** — Ctrl+C / stop.bat should close WS clients, save state,
      stop threads cleanly.

## Nice-to-have / future

- [ ] STT language from config (`stt.language` as source of truth).
- [ ] Embedding-based fact dedup in ChromaDB.
- [ ] Ollama local model as fallback tier.
- [ ] Multi-user / profile support if LAN access is ever needed.
