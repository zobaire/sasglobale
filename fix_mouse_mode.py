# -*- coding: utf-8 -*-
"""Add mouse-mode ownership to entry_ui.gd (VISIBLE on UI ready, CAPTURED on start)."""
import io

PATH = r"C:\Users\book\Desktop\fate's-pair\scripts\entry_ui.gd"

with io.open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# --- 1) In _ready(): force VISIBLE mouse while the title screen is up ---
marker = 'func _ready() -> void:'
insert_after_ready = """func _ready() -> void:
	# --- Mouse handling ---
	# The player script used to capture the mouse in its _ready(), which
	# locked the cursor to the center of the screen the moment the game
	# started - so while the title screen was up you couldn't move the
	# mouse over the webview or click START. The mouse belongs to the UI
	# while the title screen is showing; the game takes it back on START.
	Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)

"""

if marker in src and "Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)" not in src:
    src = src.replace(marker, insert_after_ready, 1)
    print("OK: VISIBLE mouse inserted in _ready()")
else:
    print("SKIP/ALREADY: _ready() mouse insert (marker found: %s)" % (marker in src))

# --- 2) In _start_game(): capture the mouse when the game begins ---
old_start = """func _start_game() -> void:
	_dbg("START pressed")
"""
new_start = """func _start_game() -> void:
	_dbg("START pressed")
"""
# The above won't match (the dbg string has an em dash) - use a smaller anchor:
anchor = "webview.set_visible(false)\n\twebview.queue_free()\n"
addition = """\t# Game is starting: lock the mouse so the player can aim.
\tInput.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
"""

if anchor in src:
    if "MOUSE_MODE_CAPTURED" not in src.split("func _start_game")[-1].split("func ")[1][:2000] or True:
        pass
    src = src.replace(anchor, anchor + addition, 1)
    print("OK: CAPTURED mouse inserted in _start_game()")
else:
    print("SKIP: _start_game() anchor not found")

with io.open(PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

print("Done.")
