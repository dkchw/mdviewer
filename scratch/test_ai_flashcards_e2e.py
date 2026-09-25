import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"BROWSER PAGE ERROR: {err}"))

        print("1. Navigating to http://127.0.0.1:2026/?file=1080_Heading.md...")
        await page.goto("http://127.0.0.1:2026/?file=1080_Heading.md", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # Enter flashcard mode
        print("2. Entering flashcard mode...")
        fc_btn = page.locator('#flashcardModeBtn')
        if await fc_btn.is_visible():
            await fc_btn.click()
            await page.wait_for_timeout(600)

        # Verify flashcard mode is active
        assert await page.locator('#flashcardView').is_visible(), "Flashcard view should be visible"
        print("✓ Flashcard mode active")

        # Verify AI Info toggle button
        ai_toggle = page.locator('#fcAiToggleBtn')
        assert await ai_toggle.is_visible(), "AI Info button should be visible in toolbar"
        print("✓ AI Info toggle button visible")

        # Click AI Info button
        print("3. Toggling AI Info side panel...")
        await ai_toggle.click()
        await page.wait_for_timeout(500)

        sidepanel = page.locator('#fcInfoSidePanel')
        assert await sidepanel.is_visible(), "AI side panel should be visible"
        is_collapsed = await sidepanel.evaluate("el => el.classList.contains('collapsed')")
        assert not is_collapsed, "AI side panel should not be collapsed"
        print("✓ AI Info side panel opened successfully")

        # Verify Prompt Select dropdown
        prompt_select = page.locator('#fcPromptSelect')
        assert await prompt_select.is_visible(), "Prompt dropdown should be visible"
        options = await prompt_select.locator('option').all_text_contents()
        print(f"✓ Prompt dropdown options: {options}")
        assert len(options) >= 4, "Should have at least 4 default prompts"

        # Verify Action Buttons
        generate_btn = page.locator('#fcGenerateBtn')
        regen_btn = page.locator('#fcRegenerateBtn')
        copy_btn = page.locator('#fcCopyBtn')
        batch_toggle_btn = page.locator('#fcBatchToggleBtn')
        assert await generate_btn.is_visible(), "Generate button should be visible"
        assert await regen_btn.is_visible(), "Regenerate button should be visible"
        assert await copy_btn.is_visible(), "Copy button should be visible"
        assert await batch_toggle_btn.is_visible(), "Batch button should be visible"
        print("✓ Action buttons (Generate, Regenerate, Copy, Batch) all visible")

        # Test Prompt Template Editor modal
        print("4. Testing Prompt Template Editor modal...")
        await page.locator('#fcPromptAddBtn').click()
        await page.wait_for_timeout(300)
        prompt_modal = page.locator('#fcPromptModal')
        assert await prompt_modal.evaluate("el => el.classList.contains('active')"), "Prompt modal should be active"

        await page.locator('#fcPromptNameInput').fill("Exam High-Yield Summary")
        await page.locator('#fcPromptSystemTextarea').fill("You are an exam coach. Provide a concise bulleted summary of key testable points.")
        await page.locator('#fcPromptSaveBtn').click()
        await page.wait_for_timeout(500)
        assert not await prompt_modal.evaluate("el => el.classList.contains('active')"), "Prompt modal should be closed"

        new_options = await prompt_select.locator('option').all_text_contents()
        assert "Exam High-Yield Summary" in new_options, "New custom prompt should be in select dropdown"
        print("✓ Custom prompt template created and added to dropdown")

        # Test Prompt Rerank modal
        print("5. Testing Prompt Rerank modal...")
        await page.locator('#fcPromptRerankBtn').click()
        await page.wait_for_timeout(300)
        rerank_modal = page.locator('#fcRerankModal')
        assert await rerank_modal.evaluate("el => el.classList.contains('active')"), "Rerank modal should be active"
        items = await page.locator('.ai-rerank-item').all()
        assert len(items) >= 5, "Should show all prompts in rerank list"
        await page.locator('#fcRerankSaveBtn').click()
        await page.wait_for_timeout(300)
        assert not await rerank_modal.evaluate("el => el.classList.contains('active')"), "Rerank modal should close"
        print("✓ Rerank modal verified")

        # Test Batch Drawer
        print("6. Testing Batch Generation Drawer...")
        await batch_toggle_btn.click()
        await page.wait_for_timeout(300)
        batch_drawer = page.locator('#fcBatchDrawer')
        assert await batch_drawer.is_visible(), "Batch drawer should be visible"

        batch_sizes = await page.locator('#fcBatchSizeSelect option').all_text_contents()
        print(f"Batch size options: {batch_sizes}")
        assert "10 cards" in batch_sizes

        trigger_options = await page.locator('#fcBatchTriggerTypeSelect option').all_text_contents()
        print(f"Trigger options: {trigger_options}")
        assert any("5 cards left" in opt for opt in trigger_options)
        assert any("80%" in opt for opt in trigger_options)

        await page.locator('#fcBatchCloseBtn').click()
        await page.wait_for_timeout(300)
        assert not await batch_drawer.is_visible(), "Batch drawer should be closed"
        print("✓ Batch drawer and auto-trigger options verified")

        # Test AI Settings modal
        print("7. Testing AI Settings modal...")
        await page.locator('#fcInfoSettingsBtn').click()
        await page.wait_for_timeout(300)
        settings_modal = page.locator('#fcAiSettingsModal')
        assert await settings_modal.evaluate("el => el.classList.contains('active')"), "Settings modal should be active"

        model_val = await page.locator('#fcModelInput').input_value()
        print(f"Model value: {model_val}")
        assert "deepseek/deepseek-flash-latest" in model_val, "Default model should be deepseek/deepseek-flash-latest"

        # Test API key visibility toggle
        key_input = page.locator('#fcApiKeyInput')
        assert await key_input.get_attribute('type') == 'password'
        await page.locator('#fcApiKeyToggleShow').click()
        assert await key_input.get_attribute('type') == 'text'
        await page.locator('#fcApiKeyToggleShow').click()
        assert await key_input.get_attribute('type') == 'password'

        await page.locator('#fcAiSettingsCancelBtn').click()
        await page.wait_for_timeout(300)
        assert not await settings_modal.evaluate("el => el.classList.contains('active')"), "Settings modal should close"
        print("✓ AI Settings modal and model verified")

        # Test Clean Up & Export modal
        print("8. Testing Clean Up & Export modal...")
        await page.locator('#fcInfoCleanupBtn').click()
        await page.wait_for_timeout(300)
        cleanup_modal = page.locator('#fcCleanupModal')
        assert await cleanup_modal.evaluate("el => el.classList.contains('active')"), "Cleanup modal should be active"
        assert await page.locator('#fcCleanCurrentCardBtn').is_visible()
        assert await page.locator('#fcCleanCurrentFileBtn').is_visible()
        assert await page.locator('#fcExportFileBtn').is_visible()
        assert await page.locator('#fcCleanAllWorkspaceBtn').is_visible()

        await page.locator('#fcCleanupDoneBtn').click()
        await page.wait_for_timeout(300)
        assert not await cleanup_modal.evaluate("el => el.classList.contains('active')"), "Cleanup modal should close"
        print("✓ Clean Up & Export modal verified")

        # Test Keyboard Shortcuts
        print("9. Testing Keyboard Shortcuts (I to toggle, Escape to close)...")
        await page.keyboard.press('i')
        await page.wait_for_timeout(300)
        assert await sidepanel.evaluate("el => el.classList.contains('collapsed')"), "Side panel should be collapsed on 'i'"

        await page.keyboard.press('i')
        await page.wait_for_timeout(300)
        assert not await sidepanel.evaluate("el => el.classList.contains('collapsed')"), "Side panel should be opened on 'i'"

        # Open a modal and press Escape
        await page.locator('#fcInfoSettingsBtn').click()
        await page.wait_for_timeout(200)
        assert await settings_modal.evaluate("el => el.classList.contains('active')")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(200)
        assert not await settings_modal.evaluate("el => el.classList.contains('active')"), "Escape should close modal"

        # Press Escape again -> closes AI side panel
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(200)
        assert await sidepanel.evaluate("el => el.classList.contains('collapsed')"), "Escape should close side panel"
        print("✓ Keyboard shortcuts (I, Escape) verified")

        # Reopen panel and capture screenshot
        await page.keyboard.press('i')
        await page.wait_for_timeout(300)
        screenshot_path = '/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/scratch/fc_ai_assistant_showcase.png'
        await page.screenshot(path=screenshot_path)
        print(f"✓ Screenshot captured: {screenshot_path}")

        print("\nALL E2E AUTOMATED TESTS PASSED SUCCESSFULLY!")
        await browser.close()

asyncio.run(run())
