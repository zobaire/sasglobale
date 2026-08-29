import sys
p = r"C:\Users\book\Desktop\fate's-pair\scripts\player.gd"
with open(p, encoding="utf-8") as f:
    lines = f.read().splitlines()
bad = []
for i, ln in enumerate(lines, 1):
    if ln[:1] == " " and ln.strip() != "" and not ln.startswith("\t"):
        bad.append((i, ln[:40]))
if bad:
    print("SPACE-INDENTED LINES:")
    for i, ln in bad[:10]:
        print(f"  line {i}: {ln!r}")
else:
    print("OK: all indented lines use tabs")
print(f"total lines: {len(lines)}")
# quick structural sanity
body = "\n".join(lines)
for token in ["func _ready", "func _input", "func _unhandled_input", "func _physics_process", "func _process"]:
    print(token, "->", "found" if token in body else "MISSING")
print("paren balance:", body.count("(") - body.count(")"))
print("curly balance:", body.count("{") - body.count("}"))
