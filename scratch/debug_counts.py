import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path='/home/dkchw/.nix-profile/bin/chromium',
            headless=True
        )
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:2026/?file=Kontext/B1%2B/L01%20Mit%20der%20Zeit.md&mode=flashcard", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        dom_info = await page.evaluate('''() => {
            return {
                title: document.title,
                fcFrontTitle: document.getElementById('fcFrontTitle')?.textContent,
                fcStats: document.getElementById('fcStats')?.textContent,
                fcHeaderMissingCount: document.getElementById('fcHeaderMissingCount')?.textContent,
                fcHeaderGenMissingBtnDisplay: document.getElementById('fcHeaderGenMissingBtn')?.style.display,
                fcSideMissingCount: document.getElementById('fcSideMissingCount')?.textContent,
                fcCleanDupCountLabel: document.getElementById('fcCleanDupCountLabel')?.textContent,
                bodyHtmlLength: document.body.innerHTML.length
            };
        }''')
        print(dom_info)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
