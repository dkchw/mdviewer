import asyncio
import json
import urllib.request
from playwright.async_api import async_playwright

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # 1. Create a dummy mistake supplement via API
        test_file = "Goethe_B1.md"
        test_slug = "H2::9999_Dummy_Mistake_For_Deletion"
        print("Creating dummy mistake supplement...")
        save_req = urllib.request.Request(
            "http://127.0.0.1:2026/api/ai/card/save",
            data=json.dumps({
                "file_path": test_file,
                "heading_slug": test_slug,
                "heading_level": 2,
                "heading_text": "9999_Dummy_Mistake_For_Deletion",
                "breadcrumb": "Unit 99 > Mistakes",
                "prompt_id": "test_prompt",
                "prompt_name": "Test Mistake Template",
                "model": "deepseek/deepseek-v4-flash-0731",
                "content": "This is a hallucinated mistake that the user wants to delete.",
                "raw_front": "9999_Dummy_Mistake_For_Deletion",
                "raw_back": "Mistake back text",
                "version": 1
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        save_res = json.loads(urllib.request.urlopen(save_req).read())
        saved_id = save_res["card"]["id"]
        print(f"Created mistake supplement id={saved_id}")

        # 2. Open app and open AI Explorer modal
        print("Opening app in browser...")
        await page.goto("http://127.0.0.1:2026/")
        await page.wait_for_selector(".tree-row", timeout=10000)

        # Handle dialog automatically by accepting confirm("Delete AI supplement...?")
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

        # Click AI Notes button in toolbar
        await page.locator("#aiExplorerToolbarBtn").click()
        await page.wait_for_selector("#fcCleanupModal.active")

        # Select scope: current file or search for 9999_Dummy
        search_input = page.locator("#fcSuppSearchInput")
        await search_input.fill("9999_Dummy")
        await page.wait_for_timeout(400)

        item_card = page.locator(f"#fcSuppItemList .fc-supp-card[data-id='{saved_id}']")
        assert await item_card.is_visible(), "Dummy mistake card should appear in search results"
        print("Found dummy mistake card in AI Explorer list!")

        # Click the 🗑️ Delete button on this card
        del_btn = item_card.locator(".fc-supp-del-btn")
        await del_btn.click()
        await page.wait_for_timeout(600)

        # Verify it is no longer in the explorer list
        assert not (await item_card.is_visible()), "Mistake card should be removed from UI immediately"
        print("Mistake card removed from UI list!")

        # Verify it is deleted from backend database via API
        check_res = json.loads(urllib.request.urlopen(f"http://127.0.0.1:2026/api/ai/card?heading={test_slug}").read())
        assert len(check_res) == 0, "Mistake card must be completely deleted from SQLite database"
        print("Verified mistake card deleted from backend database!")

        await page.screenshot(path="scratch/ai_deletion_verified.png")
        print("Saved scratch/ai_deletion_verified.png")

        await browser.close()
        print("UI DELETION TEST PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_test())
