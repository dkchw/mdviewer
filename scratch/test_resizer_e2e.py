import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/home/dkchw/.nix-profile/bin/chromium",
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1500, "height": 950})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print("Navigating to mdviewer with mode=flashcard...")
        await page.goto("http://127.0.0.1:2026/?file=DaF_Kompakt_Neu/numbered_L1_O_highlighted.md&mode=flashcard", wait_until="domcontentloaded")
        await page.wait_for_selector("#flashcardView", state="visible", timeout=10000)
        await page.wait_for_timeout(1000)

        # Open AI Side Panel using fcAiToggleBtn
        ai_panel_btn = page.locator("#fcAiToggleBtn")
        if await ai_panel_btn.is_visible():
            print("Clicking #fcAiToggleBtn to ensure side panel is open...")
            # Check if already open or collapsed
            side_panel = page.locator("#fcInfoSidePanel")
            classes = await side_panel.get_attribute("class") or ""
            if "collapsed" in classes:
                await ai_panel_btn.click()
                await page.wait_for_timeout(500)

        side_panel = page.locator("#fcInfoSidePanel")
        assert await side_panel.is_visible(), "AI side panel should be visible"
        classes = await side_panel.get_attribute("class") or ""
        assert "collapsed" not in classes, f"AI side panel should not be collapsed: {classes}"

        initial_box = await side_panel.bounding_box()
        initial_width = initial_box["width"]
        print(f"Initial AI side panel width: {initial_width}px")

        # Test 1: 1-click Preset width toggle button (#fcInfoWidthBtn)
        width_btn = page.locator("#fcInfoWidthBtn")
        assert await width_btn.is_visible(), "fcInfoWidthBtn should be visible"

        # Click 1: Normal -> Wide (~700px)
        await width_btn.click()
        await page.wait_for_timeout(300)
        box_wide = await side_panel.bounding_box()
        print(f"After 1st toggle click, width: {box_wide['width']}px")
        assert abs(box_wide["width"] - 700) < 10, f"Expected ~700px, got {box_wide['width']}"

        # Click 2: Wide -> Ultra (~75vw or ~1125px in 1500px window)
        await width_btn.click()
        await page.wait_for_timeout(300)
        box_ultra = await side_panel.bounding_box()
        print(f"After 2nd toggle click, width: {box_ultra['width']}px")
        assert box_ultra["width"] > 900, f"Expected >900px, got {box_ultra['width']}"

        # Click 3: Ultra -> Normal (420px)
        await width_btn.click()
        await page.wait_for_timeout(300)
        box_normal = await side_panel.bounding_box()
        print(f"After 3rd toggle click, width: {box_normal['width']}px")
        assert abs(box_normal["width"] - 420) < 10, f"Expected ~420px, got {box_normal['width']}"
        print("✓ 1-click preset toggle button works flawlessly (420px -> 700px -> Ultra -> 420px)")

        # Test 2: Double click resizer bar to toggle width
        resizer = page.locator("#fcInfoResizer")
        assert await resizer.is_visible(), "fcInfoResizer should be visible"
        resizer_box = await resizer.bounding_box()
        assert resizer_box["width"] >= 10, f"Resizer hit area should be wide enough (>=10px), got {resizer_box['width']}"
        print(f"Resizer hit target width: {resizer_box['width']}px")

        await resizer.dblclick()
        await page.wait_for_timeout(300)
        box_after_dblclick = await side_panel.bounding_box()
        print(f"After double-click resizer, width: {box_after_dblclick['width']}px")
        assert abs(box_after_dblclick["width"] - 700) < 10, f"Expected ~700px after dblclick, got {box_after_dblclick['width']}"

        await resizer.dblclick()
        await page.wait_for_timeout(300)
        box_after_dblclick2 = await side_panel.bounding_box()
        print(f"After 2nd double-click resizer, width: {box_after_dblclick2['width']}px")
        assert abs(box_after_dblclick2["width"] - 420) < 10, f"Expected ~420px after 2nd dblclick, got {box_after_dblclick2['width']}"
        print("✓ Double-click on resizer bar successfully toggles normal/wide width")

        # Test 3: Manual drag resizing with mouse/pointer
        resizer_box = await resizer.bounding_box()
        start_x = resizer_box["x"] + resizer_box["width"] / 2
        start_y = resizer_box["y"] + 200

        # Drag left by 180px (width should expand by ~180px: 420 -> ~600px)
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()
        await page.mouse.move(start_x - 180, start_y, steps=10)
        await page.mouse.up()
        await page.wait_for_timeout(300)

        box_after_drag = await side_panel.bounding_box()
        print(f"After drag resizing (delta -180px), width: {box_after_drag['width']}px")
        assert abs(box_after_drag["width"] - 600) < 15, f"Expected ~600px, got {box_after_drag['width']}"
        print("✓ Manual drag resizing works smoothly and accurately")

        # Test 4: Verify localStorage persistence
        saved_width = await page.evaluate("localStorage.getItem('mdv_fc_info_width')")
        print(f"Persisted width in localStorage: {saved_width}")
        assert saved_width is not None and abs(int(saved_width) - box_after_drag["width"]) < 2

        # Screenshot
        await page.screenshot(path="scratch/ai_panel_resized.png")
        print("✓ Screenshot saved to scratch/ai_panel_resized.png")

        print("Console errors:", console_errors)
        assert len(console_errors) == 0, f"Console errors detected: {console_errors}"
        print("🎉 All AI info panel resizing tests passed!")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
