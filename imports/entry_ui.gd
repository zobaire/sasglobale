extends WebView
## Fate's Pair — Entrance UI driver
##
## v5: Defers load_url() by two frames so the native webview surface has
## time to actually construct before we ask it to navigate (v4 called it
## immediately in _ready(), which sometimes ran before the native side was
## ready — page_load_started/finished never fired in that case).
## Also calls resize() explicitly instead of relying only on the automatic
## resize-on-Control-change behavior, since our Control's own rect can stay
## static (e.g. tiny default 40x40) even when full_window_size is on.
## Added start_focused toggle to test whether the webview is silently
## grabbing OS-level input focus even while rendering blank content.

@export var html_path: String = "res://ui/index.html"
@export var css_path: String = "res://ui/style.css"
@export var debug: bool = true
@export var start_focused: bool = true  ## Set false to test if the webview is stealing camera/mouse focus.

var _page_alive := false      # Page called back with {"type": "ui_ready"}
var _page_loaded := false     # page_load_finished fired at all (page exists, just maybe not "alive" yet)
var _kill_switch_fired := false
var _css_injected := false


func _ready() -> void:
	_dbg("WebView _ready() — visible=%s, size=%s" % [visible, size])
	_dbg("Plugin class registered? %s" % ClassDB.class_exists("WebView"))

	page_load_started.connect(_on_page_load_started)
	page_load_finished.connect(_on_page_load_finished)

	if not FileAccess.file_exists(html_path):
		push_error("[EntryUI] CANNOT FIND HTML FILE: " + html_path)
		return
	_dbg(">>> File exists: %s" % html_path)

	if not ipc_message.is_connected(_on_web_view_ipc_message):
		ipc_message.connect(_on_web_view_ipc_message)
		_dbg(">>> ipc_message connected (in code).")

	full_window_size = true
	devtools = debug
	focused_when_created = start_focused

	# --- Give the native webview surface time to actually construct ---
	# Calling load_url() in the same frame _ready() runs sometimes fires
	# before the native side exists yet, silently dropping the navigation
	# (no page_load_started, no page_load_finished — exactly what we saw).
	await get_tree().process_frame
	await get_tree().process_frame

	# Force a resize now, since our Control's own rect may never change
	# size/position on its own (no automatic resize signal to trigger it).
	resize()
	_dbg(">>> resize() called — size after=%s" % size)

	load_url(html_path)
	_dbg(">>> load_url() called with: %s" % html_path)

	page_load_finished.connect(_inject_css_via_eval)

	# --- Status checks + kill switch so the UI never blocks the game ---
	await get_tree().create_timer(2.0).timeout
	_dbg("2s check — visible_in_tree=%s, size=%s, page_loaded=%s, page_alive=%s" % [
		is_visible_in_tree(), size, _page_loaded, _page_alive
	])

	if debug:
		open_devtools()
		_dbg(">>> DevTools opened — check the Console tab for JS errors.")

	if not _page_alive:
		eval("""
			window.__probe = {
				hasIpc: !!(window.ipc && window.ipc.postMessage),
				readyState: document.readyState,
				hasBody: !!document.body
			};
			if (window.ipc && window.ipc.postMessage) {
				window.ipc.postMessage(JSON.stringify({type: 'probe', hasIpc: true, readyState: document.readyState}));
			}
		""")
		_dbg(">>> Probe eval() sent.")

	await get_tree().create_timer(1.5).timeout  # t ≈ 3.5s
	# Only kill if the page never even loaded. If it loaded but never pinged
	# "ui_ready", that's a JS-side bug worth seeing in DevTools rather than
	# silently freeing the UI — don't punish a page that's just being slow.
	if not _page_loaded and not _kill_switch_fired:
		push_warning("[EntryUI] Page never started loading. Firing kill switch — freeing UI so the game is playable.")
		_kill_switch_fired = true
		queue_free()

	await get_tree().create_timer(6.5).timeout  # t ≈ 10s
	_dbg("10s check — page_loaded=%s, page_alive=%s" % [_page_loaded, _page_alive])


func _on_page_load_started(url: String) -> void:
	_dbg(">>> page_load_started: %s" % url)


func _on_page_load_finished(url: String) -> void:
	_page_loaded = true
	_dbg(">>> page_load_finished: %s" % url)


func _inject_css_via_eval(_url: String) -> void:
	if _css_injected:
		return
	if not FileAccess.file_exists(css_path):
		push_warning("[EntryUI] style.css not found at %s — UI will be unstyled." % css_path)
		return
	var css: String = FileAccess.get_file_as_string(css_path)
	var js_safe_css: String = css.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
	var script := "var s=document.createElement('style');s.textContent='%s';document.head.appendChild(s);" % js_safe_css
	eval(script)
	_css_injected = true
	_dbg(">>> CSS injected into the page via eval() (%d chars)" % css.length())


func _on_web_view_ipc_message(message: String) -> void:
	_dbg("IPC message from page: %s" % message)
	var data: Variant = JSON.parse_string(message)
	if typeof(data) != TYPE_DICTIONARY:
		return

	match data.get("type", ""):
		"ui_ready":
			_page_alive = true
			_dbg(">>> PAGE IS ALIVE — HTML rendered, JS running.")
		"probe":
			_dbg(">>> Probe reply: hasIpc=%s readyState=%s" % [data.get("hasIpc", "?"), data.get("readyState", "?")])
		"js_error":
			push_error("[EntryUI] JS error reported by page: %s" % data.get("msg", "?"))
		"start":
			_start_game()
		"settings":
			print("[EntryUI] Settings clicked — not wired up yet.")
		"quit":
			get_tree().quit()


func _start_game() -> void:
	_dbg("START pressed — fading out the UI.")
	post_message(JSON.stringify({"action": "fade_out"}))
	await get_tree().create_timer(1.1).timeout
	set_visible(false)
	queue_free()


func _dbg(msg: String) -> void:
	if debug:
		print("[EntryUI] ", msg)
