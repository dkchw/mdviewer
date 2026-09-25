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

        print("Navigating to mdviewer with mode=flashcard...")
        await page.goto("http://127.0.0.1:2026/?file=DaF_Kompakt_Neu/numbered_L1_O_highlighted.md&mode=flashcard", wait_until="domcontentloaded")
        await page.wait_for_selector("#flashcardView", state="visible", timeout=10000)
        await page.wait_for_timeout(1000)

        # Open AI Side Panel using fcAiToggleBtn
        ai_panel_btn = page.locator("#fcAiToggleBtn")
        if await ai_panel_btn.is_visible():
            print("Clicking #fcAiToggleBtn...")
            await ai_panel_btn.click()
            await page.wait_for_timeout(1000)

        # Take screenshot of AI side panel
        os.makedirs("scratch", exist_ok=True)
        await page.screenshot(path="scratch/ai_side_panel.png")
        print("Saved scratch/ai_side_panel.png")

        # Open Batch drawer
        batch_toggle_btn = page.locator("#fcBatchToggleBtn")
        if await batch_toggle_btn.is_visible():
            print("Opening Batch generation drawer...")
            await batch_toggle_btn.click()
            await page.wait_for_timeout(500)
            await page.screenshot(path="scratch/batch_drawer_ui.png")
            print("Saved scratch/batch_drawer_ui.png")

        await browser.close()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
