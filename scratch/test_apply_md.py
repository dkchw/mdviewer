import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/home/dkchw/.nix-profile/bin/chromium', headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1400, "height": 900})
        await page.goto('http://127.0.0.1:2026/?file=Kontext/B1%2B/L01%20Mit%20der%20Zeit.md&mode=flashcard', wait_until='networkidle')
        await page.wait_for_timeout(2000)

        # Switch to card 1 (which has AI supplement)
        await page.evaluate("() => window.setCurrentCardIndex(1)")
        await page.wait_for_timeout(600)

        # Flip card to back face
        await page.locator("#flashcard").click()
        await page.wait_for_timeout(800)

        # Switch back view to AI mode
        await page.locator("#fcBackViewAiBtn").click()
        await page.wait_for_timeout(600)

        apply_btn = page.locator("#fcBackApplyMdBtn")
        is_apply_visible = await apply_btn.is_visible()
        print(f"Card 1 Back face 'Apply to .md' button visible: {is_apply_visible}")

        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/13_card_1_ai_back_apply_md.png")
        print("Captured 13_card_1_ai_back_apply_md.png")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
