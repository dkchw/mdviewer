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

        print("1. Navigating to File 1 in flashcard mode...")
        await page.goto("http://127.0.0.1:2026/?file=DaF_Kompakt_Neu/numbered_L1_O_highlighted.md&mode=flashcard", wait_until="domcontentloaded")
        await page.wait_for_selector("#flashcardView", state="visible", timeout=10000)
        await page.wait_for_timeout(1000)

        # Open AI Side Panel using fcAiToggleBtn
        ai_panel_btn = page.locator("#fcAiToggleBtn")
        side_panel = page.locator("#fcInfoSidePanel")
        classes = await side_panel.get_attribute("class") or ""
        if "collapsed" in classes:
            await ai_panel_btn.click()
            await page.wait_for_timeout(500)

        # Start a batch on File 1 using mode: 'new_version' so it actively runs
        print("2. Starting batch on File 1 (new_version mode)...")
        await page.evaluate("""
            window.startBatchGeneration('all', 0, {
                scope: 'all',
                concurrency: 50,
                mode: 'new_version',
                skipExisting: false,
                createNewVersion: true
            });
        """)
        await page.wait_for_timeout(1000)

        # Ensure progress box is visible
        progress_box = page.locator("#fcBatchProgressBox")
        assert await progress_box.is_visible(), "Progress box should be visible for File 1"
        status_text1 = await page.locator("#fcBpStatusText").text_content()
        print(f"File 1 batch progress: {status_text1}")

        # Now switch to File 2 via window.openFile
        print("3. Switching to File 2 via window.openFile...")
        await page.evaluate("window.openFile('DaF_Kompakt_Neu/numbered_L2_O_highlighted.md', { mode: 'flashcard' })")
        await page.wait_for_timeout(1200)

        # Check URL
        url = page.url
        print(f"Active URL: {url}")
        assert "numbered_L2_O_highlighted.md" in url

        # Start batch on File 2 while File 1 is still running!
        print("4. Starting batch on File 2 concurrently...")
        await page.evaluate("""
            window.startBatchGeneration('all', 0, {
                scope: 'all',
                concurrency: 50,
                mode: 'new_version',
                skipExisting: false,
                createNewVersion: true
            });
        """)
        await page.wait_for_timeout(1500)

        # Verify multi-batch tabs container (#fcBpTabs) is visible and contains 2 tabs!
        tabs_box = page.locator("#fcBpTabs")
        assert await tabs_box.is_visible(), "Multi-batch tabs should be visible when 2 batches run"
        tabs = await tabs_box.locator(".fc-bp-tab").all()
        print(f"Number of multi-batch tabs: {len(tabs)}")
        assert len(tabs) >= 2, f"Expected at least 2 tabs, got {len(tabs)}"

        tab1_text = await tabs[0].text_content()
        tab2_text = await tabs[1].text_content()
        print(f"Tab 1: {tab1_text}")
        print(f"Tab 2: {tab2_text}")

        # Check Stop All button is visible
        stop_all_btn = page.locator("#fcBpStopAllBtn")
        assert await stop_all_btn.is_visible(), "fcBpStopAllBtn should be visible when multiple batches are running"

        # Click Tab 1 to switch inspection to File 1
        print("5. Clicking Tab 1 to inspect File 1...")
        await tabs[0].click()
        await page.wait_for_timeout(400)
        status_after_tab1 = await page.locator("#fcBpStatusText").text_content()
        print(f"Status after clicking Tab 1: {status_after_tab1}")

        # Take screenshot of the multi-batch tabs UI
        os.makedirs("scratch", exist_ok=True)
        await page.screenshot(path="scratch/multi_batch_ui_tabs.png")
        print("Saved screenshot to scratch/multi_batch_ui_tabs.png")

        # Click Stop All button
        print("6. Clicking Stop All button...")
        await stop_all_btn.click()
        await page.wait_for_timeout(600)

        print("Console errors:", console_errors)
        assert len(console_errors) == 0, f"Console errors found: {console_errors}"
        print("🎉 Multi-Batch UI E2E test passed successfully!")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
