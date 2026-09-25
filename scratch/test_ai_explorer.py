import asyncio
import json
import urllib.request
from playwright.async_api import async_playwright

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # 1. Open main viewer
        print("Navigating to mdviewer...")
        await page.goto("http://127.0.0.1:2026")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        # 2. Check main toolbar button
        ai_toolbar_btn = page.locator("#aiExplorerToolbarBtn")
        assert await ai_toolbar_btn.is_visible(), "aiExplorerToolbarBtn should be visible in main toolbar"
        print("Main toolbar AI button visible:", await ai_toolbar_btn.text_content())

        # 3. Open AI Explorer modal from main toolbar
        await ai_toolbar_btn.click()
        await asyncio.sleep(0.8)
        cleanup_modal = page.locator("#fcCleanupModal")
        assert "active" in (await cleanup_modal.get_attribute("class")), "Modal should have active class"
        print("AI Explorer modal successfully opened!")

        # 4. Check tabs
        tab_explorer = page.locator("#fcSuppTabExplorerBtn")
        tab_cleanup = page.locator("#fcSuppTabCleanupBtn")
        assert await tab_explorer.is_visible(), "Explorer tab button should be visible"
        assert await tab_cleanup.is_visible(), "Cleanup tab button should be visible"

        # Switch scope to workspace
        scope_select = page.locator("#fcSuppScopeSelect")
        await scope_select.select_option("workspace")
        await page.wait_for_selector("#fcSuppItemList .fc-supp-card", timeout=8000)

        # Check items in list
        items = page.locator("#fcSuppItemList .fc-supp-card")
        item_count = await items.count()
        print(f"Loaded {item_count} supplement items in AI Explorer list")
        assert item_count > 0, "Should have loaded supplement cards in workspace scope"

        # Take screenshot of AI Explorer Modal
        await page.screenshot(path="scratch/ai_explorer_modal.png")
        print("Saved scratch/ai_explorer_modal.png")

        # 5. Test Expand/Collapse output
        first_toggle_btn = page.locator(".fc-supp-toggle-btn").first
        toggle_text_before = await first_toggle_btn.text_content()
        assert "Read Full Output" in toggle_text_before
        await first_toggle_btn.click()
        await asyncio.sleep(0.3)
        rendered_block = page.locator(".fc-supp-rendered").first
        assert await rendered_block.is_visible(), "Full output markdown should be rendered"
        toggle_text_after = await first_toggle_btn.text_content()
        assert "Collapse Output" in toggle_text_after
        print("Expand/Collapse full AI output verified!")

        # 6. Test Level Select filter
        level_select = page.locator("#fcSuppLevelSelect")
        await level_select.select_option("2")
        await asyncio.sleep(0.3)
        h2_items = page.locator("#fcSuppItemList .fc-supp-card")
        h2_count = await h2_items.count()
        print(f"H2 filter returned {h2_count} items")
        assert h2_count > 0, "Should have H2 items"

        # 7. Test search filter
        search_input = page.locator("#fcSuppSearchInput")
        await search_input.fill("Versorgung")
        await asyncio.sleep(0.3)
        filtered_items = page.locator("#fcSuppItemList .fc-supp-card")
        search_count = await filtered_items.count()
        print(f"Search filter for 'Versorgung' returned {search_count} items")
        assert search_count > 0, "Should match cards containing 'Versorgung'"

        # Reset search and level
        await search_input.fill("")
        await level_select.select_option("all")
        await asyncio.sleep(0.3)

        # 8. Close cleanup modal
        close_btn = page.locator("#fcCleanupCloseBtn")
        await close_btn.click()
        await asyncio.sleep(0.3)
        assert "active" not in (await cleanup_modal.get_attribute("class"))
        print("AI Explorer modal closed")

        # 9. Open a file in the workspace
        first_file = page.locator(".tree-row[data-path$='.md']").first
        if await first_file.count() > 0:
            file_path = await first_file.get_attribute("data-path")
            print("Opening file:", file_path)
            await first_file.click()
            await asyncio.sleep(1)

            # Enter flashcard mode
            fc_toggle = page.locator("#fcToggleBtn")
            if await fc_toggle.is_visible():
                await fc_toggle.click()
                await asyncio.sleep(1)
                print("Entered Flashcard mode")

                # Verify #fcFilterAi exists and can be clicked
                fc_filter_ai = page.locator("#fcFilterAi")
                assert await fc_filter_ai.is_visible(), "#fcFilterAi button should be visible in flashcard toolbar"
                await fc_filter_ai.click()
                await asyncio.sleep(0.5)
                assert "active" in (await fc_filter_ai.get_attribute("class")), "fcFilterAi should be active"
                print("✨ AI Cards filter activated in flashcard toolbar")

                # Verify AI Explorer button in flashcard toolbar
                fc_ai_explorer_btn = page.locator("#fcAiExplorerBtn")
                assert await fc_ai_explorer_btn.is_visible(), "#fcAiExplorerBtn should be visible"

                # Verify Cards Overview Sidebar
                fc_overview_btn = page.locator("#fcOverviewBtn")
                await fc_overview_btn.click()
                await asyncio.sleep(0.5)
                fc_search_ai_filter = page.locator("#fcSearchAiFilterBtn")
                assert await fc_search_ai_filter.is_visible(), "#fcSearchAiFilterBtn should be visible in sidebar"
                await fc_search_ai_filter.click()
                await asyncio.sleep(0.5)
                assert "active" in (await fc_search_ai_filter.get_attribute("class"))
                print("Sidebar '✨ AI Only' filter activated")

                # Open AI Side Panel and verify actions
                fc_ai_btn = page.locator("#fcAiBtn")
                await fc_ai_btn.click()
                await asyncio.sleep(0.5)
                assert await page.locator("#fcInfoBrowseAllBtn").is_visible(), "#fcInfoBrowseAllBtn should be visible"
                assert await page.locator("#fcInfoDeleteCardAiBtn").is_visible(), "#fcInfoDeleteCardAiBtn should be visible"
                print("Side panel AI action buttons verified (Browse All and Delete Card AI)!")

                await page.screenshot(path="scratch/ai_side_panel_actions.png")
                print("Saved scratch/ai_side_panel_actions.png")

        # 10. Test Deletion of a specific mistake / supplement via API and Explorer
        # First save a temporary test supplement
        test_file = "test_mistake_cleanup.md"
        test_slug = "H2::Mistake Heading Test"
        save_req = urllib.request.Request(
            "http://127.0.0.1:2026/api/ai/card/save",
            data=json.dumps({
                "file_path": test_file,
                "heading_slug": test_slug,
                "heading_level": 2,
                "heading_text": "Mistake Heading Test",
                "breadcrumb": "Test Folder",
                "prompt_id": "test_prompt",
                "prompt_name": "Test Mistake Output",
                "model": "deepseek/deepseek-v4-flash-0731",
                "content": "This is a hallucinated mistake output that needs deletion.",
                "raw_front": "Mistake Heading Test",
                "raw_back": "Back text",
                "version": 1
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        save_res = json.loads(urllib.request.urlopen(save_req).read())
        saved_id = save_res["card"]["id"]
        print(f"Created temporary test supplement with id={saved_id}")

        # Verify it can be retrieved via /api/ai/card?file=test_mistake_cleanup.md
        check_res = json.loads(urllib.request.urlopen(f"http://127.0.0.1:2026/api/ai/card?file={test_file}").read())
        assert any(c["id"] == saved_id for c in check_res), "Saved test supplement should be present in API"
        print("Verified test supplement exists in API")

        # Delete via /api/ai/card/delete
        del_req = urllib.request.Request(
            "http://127.0.0.1:2026/api/ai/card/delete",
            data=json.dumps({"id": saved_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        del_res = json.loads(urllib.request.urlopen(del_req).read())
        assert del_res["status"] == "ok", "Delete response should be ok"
        print("Successfully deleted test supplement via /api/ai/card/delete")

        # Verify it no longer exists
        check_after = json.loads(urllib.request.urlopen(f"http://127.0.0.1:2026/api/ai/card?file={test_file}").read())
        assert not any(c["id"] == saved_id for c in check_after), "Deleted supplement must no longer exist"
        print("Verified test supplement was completely deleted from database!")

        await browser.close()
        print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_test())
