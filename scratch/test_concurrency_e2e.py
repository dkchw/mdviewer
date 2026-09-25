import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()

        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"BROWSER PAGE ERROR: {err}"))

        # Intercept /api/ai/generate to simulate fast concurrent AI responses without requiring external OpenRouter calls
        active_requests = 0
        max_seen_concurrency = 0

        async def handle_generate(route):
            nonlocal active_requests, max_seen_concurrency
            active_requests += 1
            if active_requests > max_seen_concurrency:
                max_seen_concurrency = active_requests
            # simulate slight network latency (20ms) to allow concurrency to build up
            await asyncio.sleep(0.03)
            active_requests -= 1
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"content": "### Key Supplement Concept\\n- High-yield summary point for card.\\n- Concurrent worker generated.", "model": "deepseek/deepseek-flash-latest"}'
            )

        await page.route("**/api/ai/generate", handle_generate)

        print("1. Navigating to http://127.0.0.1:2026/?file=1080_Heading.md...")
        await page.goto("http://127.0.0.1:2026/?file=1080_Heading.md", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # Enter flashcard mode
        print("2. Entering flashcard mode...")
        fc_btn = page.locator('#flashcardModeBtn')
        if await fc_btn.is_visible():
            await fc_btn.click()
            await page.wait_for_timeout(600)

        assert await page.locator('#flashcardView').is_visible(), "Flashcard view should be visible"

        # Open AI Side Panel
        print("3. Opening AI Side Panel...")
        ai_toggle = page.locator('#fcAiToggleBtn')
        await ai_toggle.click()
        await page.wait_for_timeout(500)

        # Verify 🚀 All button
        gen_all_btn = page.locator('#fcGenerateAllBtn')
        assert await gen_all_btn.is_visible(), "fcGenerateAllBtn should be visible on action bar"
        btn_text = await gen_all_btn.text_content()
        print(f"✓ Generate All button visible with text: '{btn_text}'")
        assert "All" in btn_text, "Button text should contain 'All'"

        # Verify Batch Drawer & Concurrency input
        print("4. Opening Batch & Bulk Drawer...")
        await page.locator('#fcBatchToggleBtn').click()
        await page.wait_for_timeout(300)

        drawer = page.locator('#fcBatchDrawer')
        assert await drawer.is_visible(), "Batch drawer should be visible"

        concurrency_input = page.locator('#fcBatchConcurrencyInput')
        assert await concurrency_input.is_visible(), "Concurrency input should be visible"
        concurrency_val = await concurrency_input.input_value()
        print(f"✓ Default batch concurrency input value: {concurrency_val}")
        assert concurrency_val == "1000", f"Default concurrency should be 1000, got {concurrency_val}"

        scope_select = page.locator('#fcBatchScopeSelect')
        assert await scope_select.is_visible(), "Scope select should be visible"
        scopes = await scope_select.locator('option').all_text_contents()
        print(f"✓ Scope options: {scopes}")
        assert any("All Flashcards" in s for s in scopes)
        assert any("Unprocessed" in s for s in scopes)

        skip_existing = page.locator('#fcBatchSkipExistingCheck')
        assert await skip_existing.is_visible(), "Skip existing checkbox should be visible"
        assert await skip_existing.is_checked(), "Skip existing should be checked by default"

        start_all_btn = page.locator('#fcBatchStartAllBtn')
        assert await start_all_btn.is_visible(), "fcBatchStartAllBtn should be visible"

        # Test AI Settings modal concurrency field
        print("5. Verifying AI Settings Modal concurrency configuration...")
        await page.locator('#fcBatchCloseBtn').click()
        await page.wait_for_timeout(200)

        await page.locator('#fcInfoSettingsBtn').click()
        await page.wait_for_timeout(300)
        settings_modal = page.locator('#fcAiSettingsModal')
        assert await settings_modal.evaluate("el => el.classList.contains('active')")

        modal_concurrency = page.locator('#fcConcurrencyInput')
        assert await modal_concurrency.is_visible(), "Modal concurrency input should be visible"
        modal_concurrency_val = await modal_concurrency.input_value()
        print(f"✓ AI Settings modal concurrency value: {modal_concurrency_val}")
        assert modal_concurrency_val == "1000", f"AI settings concurrency should be 1000, got {modal_concurrency_val}"

        # Change setting to test persistence
        await modal_concurrency.fill("500")
        await page.locator('#fcAiSettingsSaveBtn').click()
        await page.wait_for_timeout(300)
        assert not await settings_modal.evaluate("el => el.classList.contains('active')")

        # Check drawer updated
        await page.locator('#fcBatchToggleBtn').click()
        await page.wait_for_timeout(200)
        new_drawer_concurrency = await page.locator('#fcBatchConcurrencyInput').input_value()
        assert new_drawer_concurrency == "500", f"Drawer concurrency should have updated to 500, got {new_drawer_concurrency}"
        print("✓ Concurrency setting saved and reflected in batch drawer")

        # Reset back to 1000
        await page.locator('#fcBatchConcurrencyInput').fill("1000")

        # Now test concurrent generation of cards
        print("6. Launching Concurrent Generation across cards...")
        # Make sure api key is present in localStorage
        await page.evaluate("() => localStorage.setItem('mdv_openrouter_api_key', 'test-key-openrouter-dummy')")
        await page.evaluate("() => { if (typeof aiSettings !== 'undefined') aiSettings.openrouter_api_key = 'test-key-openrouter-dummy'; }")

        # Select Scope: Next N cards (50 cards) with 1000 concurrency to test concurrent burst
        await page.locator('#fcBatchScopeSelect').select_option('batch')
        await page.locator('#fcBatchSizeSelect').select_option('50')
        await page.locator('#fcBatchSkipExistingCheck').uncheck() # Force generation for testing

        await page.locator('#fcBatchStartBtn').click()
        await page.wait_for_timeout(200)

        progress_box = page.locator('#fcBatchProgressBox')
        assert await progress_box.is_visible(), "Progress box should be displayed during concurrent generation"

        # Check status text
        status_text = await page.locator('#fcBpStatusText').text_content()
        current_card_text = await page.locator('#fcBpCurrentCardText').text_content()
        print(f"Progress Box Status: {status_text}")
        print(f"Progress Box Info: {current_card_text}")
        assert "workers" in current_card_text or "in-flight" in status_text or "Progress" in status_text

        # Test Pause & Resume
        print("7. Testing Pause & Resume...")
        await page.locator('#fcBpPauseBtn').click()
        await page.wait_for_timeout(300)
        pause_text = await page.locator('#fcBpPauseBtn').text_content()
        assert "Resume" in pause_text
        print("✓ Paused successfully")

        await page.locator('#fcBpPauseBtn').click()
        await page.wait_for_timeout(300)
        resume_text = await page.locator('#fcBpPauseBtn').text_content()
        assert "Pause" in resume_text
        print("✓ Resumed successfully")

        # Wait for batch completion
        print("8. Waiting for concurrent workers to complete...")
        for _ in range(30):
            await page.wait_for_timeout(300)
            if not await progress_box.is_visible():
                break

        print(f"✓ Max concurrent requests observed in flight: {max_seen_concurrency}")
        assert max_seen_concurrency > 1, f"Expected concurrent execution, but max concurrency seen was {max_seen_concurrency}"

        # Test direct "🚀 All" button
        print("9. Testing direct 🚀 All button on action bar...")
        # Reset max seen concurrency counter
        max_seen_concurrency = 0
        await page.locator('#fcGenerateAllBtn').click()
        await page.wait_for_timeout(200)
        assert await progress_box.is_visible(), "Progress box should show when clicking 🚀 All"

        # Test Stop button
        print("10. Testing Stop button...")
        await page.locator('#fcBpStopBtn').click()
        await page.wait_for_timeout(500)
        stop_toast = await page.locator('.app-toast').text_content()
        print(f"✓ Stop triggered, toast: '{stop_toast}'")

        # Take screenshot of UI
        screenshot_path = '/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/scratch/fc_ai_concurrency_showcase.png'
        await page.screenshot(path=screenshot_path)
        print(f"✓ Screenshot captured: {screenshot_path}")

        print("\nALL CONCURRENCY TESTS COMPLETED SUCCESSFULLY!")
        await browser.close()

asyncio.run(run())
