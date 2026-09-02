import asyncio, json
from playwright.async_api import async_playwright

CONSOLE = []
PAGE_ERRS = []

def dump_logs(tag):
    print(f"\n--- {tag} ---")
    for c in CONSOLE[-25:]:
        print(c)
    if PAGE_ERRS:
        print("PAGE ERRORS:")
        for e in PAGE_ERRS:
            print(e)
    else:
        print("(no page errors)")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 2560, "height": 1440})
        page.on("console", lambda m: CONSOLE.append(f"[{m.type}] {m.text[:300]}"))
        page.on("pageerror", lambda e: PAGE_ERRS.append(str(e)[:500]))

        await page.goto("http://127.0.0.1:8765", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)

        # --- 1. toggle button exists & dock hidden initially ---
        dock_open0 = await page.eval_on_selector("#codedock", "el => el.classList.contains('open')")
        print("STEP1 dock open at load:", dock_open0)

        # --- 2. click the code toggle button ---
        await page.click("#codebtn")
        await page.wait_for_timeout(250)
        dock_open1 = await page.eval_on_selector("#codedock", "el => el.classList.contains('open')")
        print("STEP2 dock open after toggle:", dock_open1)

        # --- 3. wait for CodeDock module + tree root (up to 60s — CDN deps) ---
        for i in range(120):
            has = await page.evaluate("typeof window.CodeDock !== 'undefined'")
            if has: break
            await page.wait_for_timeout(500)
        print("STEP3 CodeDock loaded:", has)
        if not has:
            dump_logs("STEP3 codedock import failed")

        tree_rows = await page.eval_on_selector_all("#cdtree .cdt-row", "els => els.map(e => e.textContent.trim())")
        print("STEP3 tree top rows:", tree_rows)

        # --- 4. expand 'Lydia' folder (first row) ---
        if tree_rows:
            await page.click("#cdtree .cdt-row.cdt-dir >> nth=0")
            await page.wait_for_timeout(1200)
            rows2 = await page.eval_on_selector_all("#cdtree .cdt-children .cdt-row", "els => els.map(e => e.textContent.trim())")
            print("STEP4 children under first root:", rows2[:15], "total:", len(rows2))

        # --- 5. navigate into 'imports' to find our scratch file ---
        # The tree is lazy; find row for 'imports' under the expanded root.
        # Note: row text starts with the ▸/▾ icon glyph, so match on title attr.
        clicked_imports = await page.evaluate("""() => {
            const rows = [...document.querySelectorAll('#cdtree .cdt-row.cdt-dir')];
            const r = rows.find(x => x.getAttribute('title') && x.getAttribute('title').replace(/\\\\/g,'/').endsWith('/imports'));
            if (r) { r.click(); return true; } return false;
        }""")
        print("STEP5 clicked imports dir:", clicked_imports)
        if clicked_imports:
            await page.wait_for_timeout(1500)
            files = await page.eval_on_selector_all("#cdtree .cdt-children .cdt-row", "els => els.map(e => ({t: e.textContent.trim(), title: e.getAttribute('title')}))")
            print("STEP5 files under imports:", [f['t'][1:] for f in files][:15])

        # --- 6. open the scratch file if present (strip icon glyph for matching) ---
        scratch = await page.evaluate("""() => {
            const rows = [...document.querySelectorAll('#cdtree .cdt-row')];
            const r = rows.find(x => x.getAttribute('title') && x.getAttribute('title').replace(/\\\\/g,'/').endsWith('imports/_codetest.md'));
            if (r) { r.click(); return true; } return false;
        }""")
        print("STEP6 scratch file clickable:", scratch)
        await page.wait_for_timeout(2500)

        # --- 7/8/9: editor tests only run if a tab actually opened ---
        tabs = await page.eval_on_selector_all("#cdtabs .cd-tab", "els => els.map(e => e.textContent.trim())")
        print("STEP7 tabs:", tabs)
        if tabs:
            meta = await page.eval_on_selector("#cdmeta", "el => el.textContent")
            print("STEP7 statusbar meta:", meta)
            try:
                await page.wait_for_selector(".cm-content", timeout=5000)
                cm_text = await page.eval_on_selector(".cm-content", "el => el.textContent.slice(0, 200)")
                print("STEP7 cm-content:", repr(cm_text))
            except Exception as ex:
                print("STEP7 cm-content MISSING:", ex)
                dump_logs("STEP7 editor missing")

            # --- 8. type into the editor & save via Ctrl+S ---
            await page.click(".cm-content")
            await page.keyboard.press("Control+End")
            await page.keyboard.type("\n# edited by headless test\n")
            await page.wait_for_timeout(400)
            dirty = await page.eval_on_selector("#cdtabs .cd-tab", "el => el.classList.contains('dirty')")
            print("STEP8 tab dirty:", dirty)
            await page.keyboard.press("Control+s")
            await page.wait_for_timeout(1500)
            status = await page.eval_on_selector("#cdstatus", "el => el.textContent")
            print("STEP8 status after save:", status)
        else:
            print("STEP7/8 SKIPPED — no tab opened (scratch file missing?)")

        # --- 9. close dock via Ctrl+B and confirm clean ---
        await page.keyboard.press("Control+b")
        await page.wait_for_timeout(400)
        dock_open2 = await page.eval_on_selector("#codedock", "el => el.classList.contains('open')")
        print("STEP9 dock closed:", not dock_open2)

        await browser.close()

    print("\n===== CONSOLE (last 40) =====")
    for c in CONSOLE[-40:]:
        print(c)
    print("\n===== PAGE ERRORS =====")
    for e in PAGE_ERRS:
        print(e)
    if not PAGE_ERRS:
        print("(none)")

try:
    asyncio.run(main())
except Exception:
    print("\n===== TEST CRASHED — console dump =====")
    for c in CONSOLE[-40:]:
        print(c)
    print("PAGE ERRORS:")
    for e in PAGE_ERRS:
        print(e)
    raise
