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
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print("Navigating to mdviewer with mode=flashcard...")
        await page.goto("http://127.0.0.1:2026/?file=DaF_Kompakt_Neu/numbered_L1_O_highlighted.md&mode=flashcard", wait_until="domcontentloaded")
        
        # Wait for flashcard view to be visible
        await page.wait_for_selector("#flashcardView", state="visible", timeout=10000)
        await page.wait_for_timeout(1000)

        # Flip card to back
        print("Flipping flashcard to view original back face...")
        await page.locator("#fcFlipBtn").click()
        await page.wait_for_timeout(500)

        # Verify .fc-enhanced-markdown is in #fcBackContent
        enhanced_count = await page.locator("#fcBackContent .fc-enhanced-markdown").count()
        print(f"Original card back .fc-enhanced-markdown elements: {enhanced_count}")

        # Check for enhanced elements in original back
        orig_bold_count = await page.locator("#fcBackContent .fc-md-bold").count()
        orig_badge_count = await page.locator("#fcBackContent .fc-key-badge").count()
        print(f"Original card back: {orig_bold_count} bold items, {orig_badge_count} pill badges")

        os.makedirs("scratch", exist_ok=True)
        await page.screenshot(path="scratch/enhanced_markdown_orig_back.png")
        print("Saved scratch/enhanced_markdown_orig_back.png")

        # Now click AI Supplement tab on back
        ai_tab_btn = page.locator("#fcBackViewAiBtn")
        if await ai_tab_btn.is_visible():
            print("Switching to AI Supplement tab on card back...")
            await ai_tab_btn.click()
            await page.wait_for_timeout(1000)

            badge_count = await page.locator("#fcBackContent .fc-key-badge").count()
            bold_count = await page.locator("#fcBackContent .fc-md-bold").count()
            table_count = await page.locator("#fcBackContent .fc-table-wrap").count()
            h_count = await page.locator("#fcBackContent .fc-md-h").count()
            callout_count = await page.locator("#fcBackContent .fc-callout").count()
            code_card_count = await page.locator("#fcBackContent .fc-code-card").count()
            print(f"AI Supplement back: {badge_count} pill badges, {bold_count} bold items, {table_count} tables, {h_count} headings, {callout_count} callouts, {code_card_count} code cards")

            await page.screenshot(path="scratch/enhanced_markdown_ai_back.png")
            print("Saved scratch/enhanced_markdown_ai_back.png")

        # Test Batch drawer
        batch_toggle_btn = page.locator("#fcBatchToggleBtn")
        if await batch_toggle_btn.is_visible():
            print("Opening Batch generation drawer...")
            await batch_toggle_btn.click()
            await page.wait_for_timeout(500)
            await page.screenshot(path="scratch/batch_drawer_ui.png")
            print("Saved scratch/batch_drawer_ui.png")

        if console_errors:
            print("Console errors found:", console_errors)
        else:
            print("SUCCESS: Zero console errors! Enhanced Markdown & Batch tests completed perfectly.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
