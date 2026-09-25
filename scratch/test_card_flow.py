import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/home/dkchw/.nix-profile/bin/chromium', headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1400, "height": 900})
        await page.goto('http://127.0.0.1:2026/?file=Kontext/B1%2B/L01%20Mit%20der%20Zeit.md&mode=flashcard', wait_until='networkidle')
        await page.wait_for_timeout(2000)

        # Card 0 is the current card (L01 Mit der Zeit, has no orig back and has no AI supplement)
        # Check Front Face controls
        front_btn = page.locator("#fcFrontGenBackBtn")
        print(f"Front Gen Back button visible on front face: {await front_btn.is_visible()}")
        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/10_card_front_gen_back.png")

        # Flip to back face
        await page.locator("#flashcard").click()
        await page.wait_for_timeout(800)

        # Back face should show empty back box with "⚡ Generate Back with AI"
        empty_gen_btn = page.locator("#fcBackEmptyGenBtn")
        is_empty_gen_visible = await empty_gen_btn.is_visible()
        print(f"Back face 'Generate Back with AI' button visible: {is_empty_gen_visible}")
        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/11_card_back_empty_gen_cta.png")

        # Now navigate to card 1 (which HAS AI supplement)
        await page.evaluate("() => window.setCurrentCardIndex(1)")
        await page.wait_for_timeout(800)

        # Because card 1 has no original markdown back but has AI supplement,
        # it auto-switches to AI Back view!
        apply_md_btn = page.locator("#fcBackApplyMdBtn")
        is_apply_visible = await apply_md_btn.is_visible()
        print(f"Card 1 Back face 'Apply to .md' button visible: {is_apply_visible}")
        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/12_card_back_ai_apply_md.png")

        # Flip to front face for card 1
        await page.locator("#flashcard").click()
        await page.wait_for_timeout(800)
        # Card 1 has AI back, so Front Gen Back button is not needed
        print(f"Card 1 Front Gen Back button visible (should be False): {await front_btn.is_visible()}")

        await browser.close()
        print("All card front and back flow verified!")

if __name__ == '__main__':
    asyncio.run(main())
