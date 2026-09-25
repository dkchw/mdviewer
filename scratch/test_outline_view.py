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

        print("Navigating to mdviewer in outline mode...")
        await page.goto("http://127.0.0.1:2026/?file=DaF_Kompakt_Neu/numbered_L1_O_highlighted.md", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        # Expand outline or scroll slightly
        await page.screenshot(path="scratch/outline_view.png")
        print("Saved scratch/outline_view.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
