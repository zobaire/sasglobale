# Lydia — Improvement Steps

Status: plan agreed 2026-09-02. Order matters: do A (quick bug fixes) first,
then B (finish Coding Mode), then C (chat quality), and use D when installing
on a new machine. Every section points at the actual file to touch.

---

## A. Quick UI bug fixes (frontend, ~1 hour total)

Status: DONE 2026-09-02 (commit 36399e6). A1's backend half needs a Lydia
restart to load (frontend halves A2-A5 are live per page refresh).

### A1. Status orb stuck on "thinking" after every text chat reply
- Symptom: after you TYPE a message, the orb keeps pulsing "thinking" until
  your next interaction. Voice path is fine because it broadcasts
  Speaking... / Ready.
- Root cause: the WebSocket chat path in `brain/web.py` broadcasts
  "Thinking..." -> streams -> final `assistant` event, then NOTHING. No
  status is broadcast when TTS starts or finishes.
- Fix:
  1. In the user_text handler of `brain/web.py`, broadcast a `Speaking...`
     status right before TTS is triggered, and `connected` after it ends
     (mirror what `handle_wake` does).
  2. Verify in `ui/indexV2.html` that the `Speaking...`/`connected` cases
     already exist (they do, for voice) so the chat path just needs the
     broadcasts.

### A2. Graph wipes routine + note bubbles when a file is imported or you say "remember"
- Symptom: all routine bubbles and imported-file note bubbles disappear the
  first time anything lands in memory; they only return on full page reload.
- Root cause: UI `handle()` case `'memory'` calls
  `updateGraph([], '', remembered)` with EMPTY routines and notes, so
  `updateGraph` rebuilds the node map without them.
- Fix in `ui/indexV2.html`: keep `lastRoutines` / `lastNotes` populated from
  the `state` event and pass those into `updateGraph` on `memory` events
  instead of empty arrays.

### A3. Guard JSON.parse in the WebSocket message handler
- One malformed frame currently kills the whole `ws.onmessage` handler
  silently (throws before later cases run).
- Fix: wrap the `JSON.parse` in try/catch, log the raw frame, and keep the
  loop alive.

### A4. "Thoughts" panel: dead code + can't scroll while streaming
- Backend only ever sends `thought_delta` (verified by grepping every
  `broadcast()` in `brain/`), yet the UI has a `case 'thought'` handler that
  never fires.
- Every token forces `scrollTop = scrollHeight`, so you cannot scroll up to
  read earlier reasoning while it streams.
- Fix in `ui/indexV2.html`:
  1. Handle `thought_delta` as one streaming bubble PER TURN.
  2. Close / label the bubble on the final `assistant` event.
  3. Only auto-scroll if the user is already at the bottom (check
     `scrollHeight - scrollTop < threshold` before forcing scroll).

### A5. Crisp canvas on hi-DPI screens
- The graph canvas ignores `devicePixelRatio`, so neon glow looks soft on
  scaled displays. Scale the context once per resize.

---

## B. Coding Mode — finish it (~half a day)

Status: DONE 2026-09-02 (live in `ui/indexV2.html` + `ui/codedock.mjs` +
`brain/web.py`, verified end-to-end by the Playwright headless test in
`_e2e_test.py`). The bug that kept the whole dock dead: `codedock.mjs`
imported `closeHistory` from `@codemirror/commands`, which does NOT export
it in ANY 6.x CDN build — a missing named export is a hard SyntaxError at
ES-module link time, so `window.CodeDock` never initialized and the lazy
`import('/codedock.mjs')` promise rejected with a console warning only.
Fix: removed the import + its guarded call (`ui/codedock.mjs`), plus two
import-map fixes from earlier in the session: `@lezer/json` 1.0.0 -> 1.0.3
(404) and added the missing `@lezer/lr@1.4.10` dependency.

Backend endpoints already exist in `brain/web.py` but the UI never calls
them; the file tree is a static "step 3 coming" stub.

### B1. Real folder tree
1. Add `GET /api/code/tree?path=...` in `brain/web.py` that lists
   directories/files under the allowlisted roots (`_CODE_ROOTS`), with a
   depth limit and gitignore-style exclusions (`.git`, `node_modules`,
   `__pycache__`, `.venv`, `memory_data`).
2. In `ui/indexV2.html` render the result as a collapsible tree in `#cdtree`
   (replace the stub text). Clicking a file opens it.

### B2. Wire open + save through real paths
1. Clicking a tree file -> `GET /api/code/read?path=...` (endpoint exists,
   currently dead) -> open in a CodeMirror tab.
2. Save flow, in priority order:
   - Chromium: keep the File System Access API path (writable handle).
   - Everywhere else / no handle: `POST /api/code/save` with the real path
     so edits persist to disk, then toast the saved path.
3. Show unsaved-changes state (dot on the tab) and confirm before closing a
   tab or the dock.

### B3. Lazy-load the editor
- CodeMirror + ~15 CDN modules load and instantiate an EditorView on every
  page load even if Coding Mode is never opened. Dynamically inject the
  scripts on first dock open instead.

---

## C. Everyday chat quality

### C1. Markdown rendering (biggest readability win)
- Raw text today: no code highlighting, no copy buttons, flat lists.
- Add `marked` + a highlighter. SECURITY: escape HTML first, then transform.
  Render only on the final `assistant` event; keep raw text while streaming.

### C2. Copy button on code blocks
- Small CSS/JS addition in the renderer from C1.

### C3. Skip semantic search for trivial queries (backend latency)
- Every message triggers a Chroma search, even "what's 2+2". In
  `brain/main.py` process_request: skip memory search for very short queries
  or pure math / greetings.

### C4. Cache load_config()
- `load_config()` re-reads config.yaml + .env on EVERY call (per request,
  per TTS sentence, per battery poll). Cache the parsed result and reload
  only when the file mtime changes.

### C5. Slice the system prompt's notes
- The prompt includes every line of notes.md via `_load_legacy_facts_text()`.
  It grows unbounded as files get imported. Keep only the most recent ~30-40
  entries in the prompt.

### C6. Stop pointless frontend work
- Pause the force-sim + glow repaint when nothing changed or when the Coding
  dock is open.
- Don't persist chat to localStorage every ~500ms while tokens are
  streaming — skip persistence during an active stream.

---

## D. Fresh-laptop install — "stuck at starting backend" (run.bat)

How run.bat works: prints `starting backend...`, launches
`python -m brain.main` in a MINIMIZED window, then polls 127.0.0.1:8765 for
up to 40 seconds. If it prints `backend didn't start`, the real error is in
that minimized LYDIA_BACKEND window.

### D1. Checklist before running
1. `pip install -r requirements.txt` — requirements.txt NOW includes
   `faster-whisper` (local STT is the default provider) + optional
   `openwakeword`. Installing an older copy of the repo (without these) is
   the most likely reason voice/wake features silently die on a new PC.
2. Copy `.env.example` -> `.env` and fill in real keys (DEEPSEEK_API_KEY is
   required; Gemini/Groq keys needed if you switch STT fallbacks).
3. Use Python 3.11 or 3.12. chromadb / ctranslate2 / faster-whisper wheels
   are happiest there.
4. Port 8765 must be free: `netstat -ano | findstr 8765` — kill the owning
   PID if something else is listening.
5. First boot downloads the faster-whisper `small` model (~500 MB) in a
   background thread. It needs internet and can make the backend look hung
   for a few minutes on a slow connection. Let it finish once.

### D2. Diagnose the real error
1. Do NOT launch via run.bat. Open a normal terminal in the project folder
   and run:
   `python -m brain.main`
   The full traceback prints there instead of hiding in a minimized window.
2. Check `backend_test.log` for startup errors (it's written by the backend).
3. Common causes seen so far:
   - Missing package that the config assumes (faster-whisper / openwakeword).
   - Empty or partial `.env` (config loads fine, first request crashes).
   - Firewall blocking python the first time (allow it).
   - Flaky network to Discord gateway (`aiohttp` ClientConnectorError in the
     log) — cosmetic if it retries, fatal if the bot token login fails.
4. If wake word is the problem and you don't want it: in config.yaml set
   `wake_word.enabled: false` and use the keyboard shortcut / click-to-talk.

### D3. After it starts
- UI: http://localhost:8765 (or the port in config.yaml `ui.port`).
- Close the Lydia window to shut the whole system down (that's by design).

---

## E. Focus mode + fullscreen coding IDE (added 2026-09-02)

Status: DONE in `ui/indexV2.html` (backend untouched). Served live per
refresh, no restart needed. JS syntax verified with `node --check`; server
serves the updated page (checked 127.0.0.1:8765).

What changed, in one file:
1. **Focus / zen toggle** — new `#zen` button in the composer (target icon).
   `body.focus` fades out Memory, Thoughts and Plans panels (they keep
   updating in the background; state is untouched). Default ON — matches
   the "clean chat + coding + graph" request. State persists in
   `localStorage['lydia.focus.v1']`. Click again to bring the brain panels
   back for demos.
2. **Coding Mode opens FULLSCREEN** — `</>` (or Ctrl+B) now enters a
   whole-screen IDE (`#codedock.full`, z-index 70): `top/right/bottom 0`,
   `width 100vw`, radius 0, tree widens to 290px, header/status padded.
   `body.code-full` hides HUD, batteries, thoughts, plans, memory, hint,
   detail popup and the chat panel so it's pure code over the living graph
   (the dock glass is translucent — animation still glows behind it).
3. **Chat while coding** — chat tucks into a `#chatpill` (bottom-left,
   visible when fullscreen & chat tucked). Clicking it pops `#chatwrap`
   back as an overlay (`.chat-peek`, bottom-center, z-index 85, max-height
   64vh) with a `#chatx` close button. Voice still works with chat hidden.
4. **Esc / toggle chain** — Ctrl+B or `</>` opens/closes coding (always
   opens full). `#cdfull` (⛶/▣ in the dock header) shrinks fullscreen back
   to the old 560px docked panel or expands again. Esc walks down:
   chat overlay -> docked panel -> closed.
5. Ctrl+K pops the chat open (if tucked) and focuses the input.
6. `#toast` raised to z-index 96 so save errors / model toasts show above
   the fullscreen dock.

CSS notes for future edits:
- `#codedock.open,#codedock.full` carries the geometry transition
  (width/top/right/bottom/border-radius) — plain `#codedock` would lose the
  specificity battle to `#codedock.open`.
- `body.code-full #chatwrap.chat-peek` must stay !important to beat the
  `body.code-full #chatwrap` hidden rule.

---

## Definition of done for this pass
- [x] A1-A5 done -> orb never sticks, graph keeps bubbles, thoughts readable
      (A1 backend half pending a Lydia restart)
- [x] B1-B3 done -> open a folder, browse, edit, save to real disk, no
      full-page reloads needed (verified 2026-09-02: tree expands
      `Lydia`/`fate's-pair`, file opens in a CodeMirror tab, Ctrl+S writes
      back to real disk via POST /api/code/save, Ctrl+B closes clean,
      zero console/page errors)
- [x] E done -> focus mode hides brain panels; Coding Mode opens as a
      fullscreen IDE; chat tucks into a pill and pops open on demand;
      Esc/⛶ walk the states (verified: server serves the updated page,
      node --check passes)
- [ ] C1 done -> code answers render with highlight + copy
- [ ] D: fresh laptop boots Lydia to "ready at http://localhost:8765"
