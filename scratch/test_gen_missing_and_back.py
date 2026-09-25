import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path='/home/dkchw/.nix-profile/bin/chromium',
            headless=True
        )
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1400, "height": 900})

        url = "http://127.0.0.1:2026/?file=Kontext/B1%2B/L01%20Mit%20der%20Zeit.md&mode=flashcard"
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2500)

        # 1. Check Header "Gen Missing" Button
        header_btn = page.locator("#fcHeaderGenMissingBtn")
        is_header_btn_visible = await header_btn.is_visible()
        missing_count_text = await page.locator("#fcHeaderMissingCount").text_content()
        print(f"Header 'Gen Missing' button visible: {is_header_btn_visible}, missing count: {missing_count_text}")
        assert is_header_btn_visible, "Header Gen Missing button should be visible!"

        # 2. Check Side Panel Missing Count
        # Open side panel if collapsed
        side_panel = page.locator("#fcInfoSidePanel")
        if "collapsed" in (await side_panel.get_attribute("class") or ""):
            await page.locator("#fcAiToggleBtn").click()
            await page.wait_for_timeout(600)

        side_missing_count = await page.locator("#fcSideMissingCount").text_content()
        print(f"Side panel missing count: {side_missing_count}")
        assert side_missing_count == missing_count_text, f"Side count ({side_missing_count}) should match header ({missing_count_text})"

        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/06_header_and_side_gen_missing.png")
        print("Captured 06_header_and_side_gen_missing.png")

        # 3. Check AI Explorer / Discrepancy Banner Missing Button
        await page.locator("#fcInfoBrowseAllBtn").click()
        await page.wait_for_timeout(1000)

        discrepancy_banner = page.locator("#fcSuppDiscrepancyBanner")
        is_banner_visible = await discrepancy_banner.is_visible()
        banner_text = await page.locator("#fcSuppDiscrepancyText").inner_text()
        print(f"Discrepancy banner visible: {is_banner_visible}")
        print(f"Banner text: {banner_text}")

        modal_gen_btn = page.locator("#fcSuppGenMissingBtn")
        is_modal_gen_btn_visible = await modal_gen_btn.is_visible()
        modal_missing_num = await page.locator("#fcSuppModalMissingNum").text_content()
        print(f"Modal Gen Missing button visible: {is_modal_gen_btn_visible}, count: {modal_missing_num}")
        assert is_modal_gen_btn_visible, "Modal Gen Missing button should be visible!"

        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/07_discrepancy_gen_missing_button.png")
        print("Captured 07_discrepancy_gen_missing_button.png")

        # Close cleanup modal
        await page.locator("#fcCleanupCloseBtn").click()
        await page.wait_for_timeout(500)

        # 4. Check Card Back / Empty Section / Apply to .md
        # Navigate to a card and flip
        # Check current card back
        await page.locator("#flashcard").click()
        await page.wait_for_timeout(800)

        # In card back, check if AI Back has Apply to .md button
        ai_tab = page.locator("#fcBackViewAiBtn")
        await ai_tab.click()
        await page.wait_for_timeout(600)

        apply_md_btn = page.locator("#fcBackApplyMdBtn")
        is_apply_btn_visible = await apply_md_btn.is_visible()
        print(f"Card Back 'Apply to .md' button visible: {is_apply_btn_visible}")

        # Check side panel apply md btn
        side_apply_btn = page.locator("#fcInfoApplyMdBtn")
        is_side_apply_visible = await side_apply_btn.is_visible()
        print(f"Side Panel 'Apply to .md' button visible: {is_side_apply_visible}")

        await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/08_ai_back_and_apply_to_md.png")
        print("Captured 08_ai_back_and_apply_to_md.png")

        # 5. Check empty card back handling
        cards_info = await page.evaluate('''() => {
            const list = window.getFlashcardList ? window.getFlashcardList() : [];
            const aiCards = window.getCurrentFileAiCards ? window.getCurrentFileAiCards() : new Map();
            return list.map((c, i) => {
                let text = '';
                if (c.card_content !== undefined) text = c.card_content;
                const slug = c.slug || `H${c.level}::${(c.text||'').trim()}`;
                const hasAi = aiCards && (aiCards.has(slug) || aiCards.has(`H${c.level}::${(c.text||'').trim()}`));
                return { index: i, text: c.text, hasOrig: !!(text && text.trim()), hasAi: !!hasAi };
            });
        }''')
        
        empty_cards = [c for c in cards_info if not c['hasOrig']]
        print(f"Total cards: {len(cards_info)}, Cards without original markdown body: {len(empty_cards)}")
        if empty_cards:
            target = empty_cards[0]
            print(f"Testing empty card at index {target['index']}: '{target['text']}' (hasAi: {target['hasAi']})")
            await page.evaluate(f'''() => {{
                if (window.setCurrentCardIndex) window.setCurrentCardIndex({target['index']});
            }}''')
            await page.wait_for_timeout(600)
            await page.wait_for_timeout(600)
            
            # Check front button if not hasAi
            if not target['hasAi']:
                front_gen_btn = page.locator("#fcFrontGenBackBtn")
                print(f"Front Gen Back button visible for empty card without AI: {await front_gen_btn.is_visible()}")

            await page.screenshot(path="/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/09_empty_card_behavior.png")
            print("Captured 09_empty_card_behavior.png")

        await browser.close()
        print("All tests and verifications completed successfully!")

if __name__ == '__main__':
    asyncio.run(main())
