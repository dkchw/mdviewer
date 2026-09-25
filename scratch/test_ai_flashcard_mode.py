import asyncio
import json
import urllib.request
from playwright.async_api import async_playwright

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # Open Goethe_B1.md in flashcard mode
        print("Opening app...")
        await page.goto("http://127.0.0.1:2026/")
        await page.wait_for_selector(".tree-row", timeout=10000)

        file_item = page.locator(".tree-row.file:has-text('Goethe_B1.md')").first
        await file_item.click()
        await page.wait_for_timeout(1000)

        # Enter flashcard mode
        fc_btn = page.locator("#flashcardModeBtn")
        await fc_btn.click()
        await page.wait_for_timeout(800)

        # 1. Test #fcFilterAi ("✨ AI Cards") button
        filter_ai_btn = page.locator("#fcFilterAi")
        assert await filter_ai_btn.is_visible(), "fcFilterAi should be visible"
        print("Filter AI button text:", await filter_ai_btn.text_content())
        await filter_ai_btn.click()
        await page.wait_for_timeout(500)
        assert "active" in (await filter_ai_btn.get_attribute("class")), "fcFilterAi should be active"

        # Check flashcard counter
        fc_stats_text = await page.locator("#fcStats").text_content()
        fc_cards_count = await page.locator("#fcCardCount").text_content()
        print(f"Flashcard mode filtered to AI cards: stats={fc_stats_text}, cardCount={fc_cards_count}")
        assert int(fc_cards_count) > 0, "Should have AI flashcards loaded"

        # 2. Test Cards Overview sidebar
        overview_toggle = page.locator("#fcOverviewBtn")
        await overview_toggle.click()
        await page.wait_for_timeout(500)
        sidebar = page.locator("#fcRightSidebar")
        assert not ("collapsed" in (await sidebar.get_attribute("class"))), "Sidebar should be open"

        # Check AI Only button in sidebar
        sb_ai_btn = page.locator("#fcSearchAiFilterBtn")
        assert await sb_ai_btn.is_visible(), "fcSearchAiFilterBtn should be visible in sidebar"
        await sb_ai_btn.click()
        await page.wait_for_timeout(300)
        assert "active" in (await sb_ai_btn.get_attribute("class")), "fcSearchAiFilterBtn should be active"

        # Check that items in overview list have the delete AI button (.fc-item-delete-ai-btn)
        del_btns = page.locator("#fcCardList .fc-item-delete-ai-btn")
        del_count = await del_btns.count()
        print(f"Found {del_count} delete AI buttons in overview sidebar list")
        assert del_count > 0, "Overview items with AI should have delete buttons"

        # 3. Test AI side panel buttons
        ai_panel_toggle = page.locator("#fcAiToggleBtn")
        await ai_panel_toggle.click()
        await page.wait_for_timeout(500)

        browse_all_btn = page.locator("#fcInfoBrowseAllBtn")
        del_card_ai_btn = page.locator("#fcInfoDeleteCardAiBtn")
        assert await browse_all_btn.is_visible(), "fcInfoBrowseAllBtn should be visible in side panel"
        assert await del_card_ai_btn.is_visible(), "fcInfoDeleteCardAiBtn should be visible in side panel"
        print("Side panel buttons verified!")

        # 4. Click Browse All (📑) from side panel -> opens AI Explorer modal
        await browse_all_btn.click()
        await page.wait_for_timeout(800)
        modal = page.locator("#fcCleanupModal")
        assert "active" in (await modal.get_attribute("class")), "Modal should open from side panel browse button"
        print("Modal successfully opened from side panel browse button!")

        # Test Study button from within explorer modal
        first_study_btn = page.locator("#fcSuppItemList .fc-supp-study-btn").first
        await first_study_btn.click()
        await page.wait_for_timeout(800)
        assert "active" not in (await modal.get_attribute("class")), "Modal should close when studying a card"
        print("Study button clicked, modal closed, navigated to card!")

        await page.screenshot(path="scratch/ai_flashcard_mode_verified.png")
        print("Saved scratch/ai_flashcard_mode_verified.png")

        await browser.close()
        print("ALL FLASHCARD MODE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_test())
