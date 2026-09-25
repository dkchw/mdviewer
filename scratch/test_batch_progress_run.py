import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print("1. Opening app...")
        await page.goto("http://127.0.0.1:2026/")
        await page.wait_for_selector(".tree-row", timeout=10000)

        # Open Goethe_B1.md
        file_item = page.locator(".tree-row.file:has-text('Goethe_B1.md')").first
        await file_item.click()
        await page.wait_for_timeout(1000)

        # Enter flashcard mode
        fc_btn = page.locator("button:has-text('Flashcard')").first
        await fc_btn.click()
        await page.wait_for_timeout(1000)

        # Open AI side panel
        fc_ai_toggle = page.locator("#fcAiToggleBtn")
        if await fc_ai_toggle.is_visible():
            await fc_ai_toggle.click()
            await page.wait_for_timeout(500)

        # Open Batch Drawer
        batch_drawer_btn = page.locator("button:has-text('Batch...')").first
        await batch_drawer_btn.click()
        await page.wait_for_timeout(500)

        # Set Scope to 'Current Batch (10 cards)' so it's fast
        scope_select = page.locator("#fcBatchScopeSelect")
        await scope_select.select_option("batch")
        await page.wait_for_timeout(300)

        print("2. Clicking 'Start Batch'...")
        start_btn = page.locator("#fcBatchStartBtn")
        await start_btn.click()
        await page.wait_for_timeout(500)

        # Progress box should be visible
        progress_box = page.locator("#fcBatchProgressBox")
        assert await progress_box.is_visible()
        print("Progress box is visible!")

        # Wait a moment for polling
        await page.wait_for_timeout(1500)
        status_text = await page.locator("#fcBpStatusText").text_content()
        card_text = await page.locator("#fcBpCurrentCardText").text_content()
        print("Status text:", status_text)
        print("Current card text:", card_text)

        await page.screenshot(path="scratch/batch_running_progress.png")
        print("Saved scratch/batch_running_progress.png")

        assert len(console_errors) == 0, f"Console errors: {console_errors}"
        await browser.close()
        print("✓ All batch progress tests passed with 0 console errors!")

if __name__ == "__main__":
    asyncio.run(main())
