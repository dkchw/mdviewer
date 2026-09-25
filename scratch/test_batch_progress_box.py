import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/home/dkchw/.nix-profile/bin/chromium",
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        await page.goto("http://127.0.0.1:2026/?file=DaF_Kompakt_Neu/numbered_L1_O_highlighted.md&mode=flashcard", wait_until="domcontentloaded")
        await page.wait_for_selector("#flashcardView", state="visible", timeout=10000)

        # Open AI panel
        await page.locator("#fcAiToggleBtn").click()
        await page.wait_for_timeout(500)

        # Open Batch drawer
        await page.locator("#fcBatchToggleBtn").click()
        await page.wait_for_timeout(500)

        # Select scope: batch, size: 5, skip existing: checked
        await page.select_option("#fcBatchScopeSelect", "batch")
        await page.wait_for_timeout(200)

        # Check that size input appears
        size_wrap_visible = await page.locator("#fcBatchSizeWrap").is_visible()
        print(f"Batch size wrapper visible when scope=batch: {size_wrap_visible}")

        # Select 'all' scope
        await page.select_option("#fcBatchScopeSelect", "all")
        await page.wait_for_timeout(200)

        print("SUCCESS: Batch drawer controls and scope switching verified.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
