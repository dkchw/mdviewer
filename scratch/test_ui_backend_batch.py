import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print("Navigating to http://127.0.0.1:2026/ ...")
        await page.goto("http://127.0.0.1:2026/")
        await page.wait_for_selector(".tree-row", timeout=10000)

        # Open Goethe_B1.md or first file
        file_item = page.locator(".tree-row.file:has-text('Goethe_B1.md')").first
        await file_item.click()
        await page.wait_for_timeout(1000)

        # Enter flashcard mode by clicking the Flashcard toolbar button
        fc_btn = page.locator("button:has-text('Flashcard')").first
        await fc_btn.click()
        await page.wait_for_timeout(1000)

        # Open AI side panel by pressing 'i' or clicking AI toggle
        fc_ai_toggle = page.locator("#fcAiToggleBtn")
        if await fc_ai_toggle.is_visible():
            await fc_ai_toggle.click()
            await page.wait_for_timeout(500)

        await page.screenshot(path="scratch/flashcard_mode_opened.png")

        # Check fcGenerateAllBtn
        fc_gen_all = page.locator("#fcGenerateAllBtn")
        assert await fc_gen_all.is_visible()
        btn_text = await fc_gen_all.text_content()
        print("Generate all button text:", btn_text)

        # Open Batch Drawer
        batch_drawer_btn = page.locator("button:has-text('Batch...')").first
        await batch_drawer_btn.click()
        await page.wait_for_timeout(500)

        concurrency_input = page.locator("#fcBatchConcurrencyInput")
        assert await concurrency_input.is_visible()
        concurrency_val = await concurrency_input.input_value()
        print("Batch Concurrency value:", concurrency_val)
        assert concurrency_val == "1000"

        mode_select = page.locator("#fcBatchModeSelect")
        assert await mode_select.is_visible()
        mode_val = await mode_select.input_value()
        print("Batch mode select value:", mode_val)

        # Screenshot batch drawer
        await page.screenshot(path="scratch/backend_batch_drawer.png")
        print("Screenshot saved to scratch/backend_batch_drawer.png")

        print("Console errors:", console_errors)
        assert len(console_errors) == 0, f"Errors found: {console_errors}"
        await browser.close()
        print("✓ Playwright test completed with 0 errors!")

if __name__ == "__main__":
    asyncio.run(main())
