# Lydia Feature Patch: Equal N-Way Window Splitting

## Problem
Windows 11's built-in snap (`Win+Arrow`) only supports fixed shapes — halves and quadrants (2 or 4 windows). It cannot put 3 (or 5, or any N) specific apps side by side at equal width, e.g. "put Discord, Spotify, and Brave side by side." `set_window_layout` (from the earlier window-management patch) only knows fixed named zones (`left-half`, `top-right`, etc.), so it can't do this either.

## Fix
Add a new function that divides the screen into however many equal columns (or rows) are needed for the apps given, in the order given.

---

## 1. Add to `window_manager.py`

This assumes `window_manager.py` already exists from the earlier window-management patch (with `get_screen_size`, `find_window`, etc. already defined). Append this function to that file:

```python
def split_windows_equally(apps: list, direction: str = "horizontal") -> list:
    """
    Split the screen into N equal zones and assign one app per zone, in order.
    direction: "horizontal" (side-by-side columns) or "vertical" (stacked rows)

    Example: split_windows_equally(["discord", "spotify", "brave"])
    -> each gets exactly 1/3 of the screen width, side by side.
    """
    results = []
    n = len(apps)
    if n == 0:
        return results

    w, h = get_screen_size()

    for i, app_name in enumerate(apps):
        win = find_window(app_name)
        if not win:
            results.append(f"Couldn't find a window matching '{app_name}'.")
            continue

        hwnd = win["hwnd"]
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        if direction == "horizontal":
            col_width = w // n
            x, y, width, height = i * col_width, 0, col_width, h
        else:  # vertical
            row_height = h // n
            x, y, width, height = 0, i * row_height, w, row_height

        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, x, y, width, height, win32con.SWP_SHOWWINDOW
        )
        results.append(f"Placed {win['process']} in column {i+1}/{n}.")

    return results
```

No new imports needed — it reuses `win32gui`, `win32con`, `get_screen_size`, and `find_window` already present in the file.

---

## 2. Tool schema

Add this alongside the other window-management tool schemas (`focus_window`, `set_window_layout`, etc.):

```python
{
    "name": "split_windows_equally",
    "description": "Split the screen into N equal-width (or equal-height) zones and place one app per zone, in the order given. Use this when the user wants several specific apps arranged side by side at the same size — a shape Windows' built-in snap can't do for anything other than 2 or 4 windows.",
    "parameters": {
        "type": "object",
        "properties": {
            "apps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "App names in left-to-right (or top-to-bottom) order, e.g. ['discord', 'spotify', 'brave']"
            },
            "direction": {
                "type": "string",
                "enum": ["horizontal", "vertical"],
                "description": "horizontal = side-by-side columns, vertical = stacked rows"
            }
        },
        "required": ["apps"]
    }
}
```

---

## 3. Dispatcher wiring

In the tool dispatch table, next to the other window-management entries:

```python
from window_manager import split_windows_equally

TOOL_DISPATCH["split_windows_equally"] = lambda args: split_windows_equally(
    args["apps"], args.get("direction", "horizontal")
)
```

---

## 4. System prompt addition

Add this to Lydia's system prompt, near the existing window-management instructions:

```
Use split_windows_equally when the user names 3 or more specific apps they
want arranged side by side at equal size (e.g. "put Discord, Spotify, and
Brave side by side"). set_window_layout only covers fixed halves/quadrants —
this covers any number of apps, split evenly.

The order of apps in the list determines left-to-right (or top-to-bottom)
placement, so preserve the order the user names them in.
```

---

## 5. Optional cleanup

`split_windows_equally` with 2 apps and `direction="horizontal"` produces the same result as `set_window_layout({"app1": "left-half", "app2": "right-half"})`. If it simplifies things, route all "N apps side by side" requests (including 2) through `split_windows_equally`, and keep `set_window_layout` only for cases that need a *specific* named zone like `top-right` or `full` rather than an even split.

---

## 6. Test

Run directly on the Windows machine to confirm it works before wiring into the tool loop:

```python
from window_manager import split_windows_equally

# Open Discord, Spotify, and Brave first, then run:
print(split_windows_equally(["discord", "spotify", "brave"]))
```

Expected: three windows placed as equal-width columns covering the full screen, left to right in that order.
