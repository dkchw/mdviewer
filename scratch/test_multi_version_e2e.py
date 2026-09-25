import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/home/dkchw/.nix-profile/bin/chromium')
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()

        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"BROWSER PAGE ERROR: {err}"))

        # Mock AI generation endpoint
        async def handle_generate(route):
            await asyncio.sleep(0.05)
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"content": "### Enhanced AI Study Notes (v2)\\n- Deep dive explanation point.\\n- Key concept for active recall learning.", "model": "deepseek/deepseek-flash-latest"}'
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

        # Flip to card back
        print("3. Flipping card to view back face...")
        await page.locator('#fcFlipBtn').click()
        await page.wait_for_timeout(600)
        assert await page.locator('#flashcard').evaluate("el => el.classList.contains('flipped')"), "Card should be flipped"

        # Verify Back View Tabs (Original vs AI Supplement)
        orig_tab = page.locator('#fcBackViewOrigBtn')
        ai_tab = page.locator('#fcBackViewAiBtn')
        assert await orig_tab.is_visible(), "Original tab should be visible on back face"
        assert await ai_tab.is_visible(), "AI Supplement tab should be visible on back face"
        assert await orig_tab.evaluate("el => el.classList.contains('active')"), "Original tab should be active by default"
        print("✓ Card back view tabs verified (Original active)")

        # Verify swapping into AI Supplement on card back
        print("4. Swapping card back to AI Supplement mode...")
        await ai_tab.click()
        await page.wait_for_timeout(400)
        assert await ai_tab.evaluate("el => el.classList.contains('active')"), "AI Supplement tab should be active"
        assert await page.locator('#fcBackAiBar').is_visible(), "fcBackAiBar should be visible when swapped to AI mode"
        
        # Verify AI content rendered in back card
        back_content = await page.locator('#fcBackContent').inner_html()
        assert "fc-back-ai-wrapper" in back_content, "Back content should render AI wrapper"
        assert "✨" in back_content or "v1" in back_content, "Back content should show AI banner"
        print("✓ AI Supplement successfully swapped into card back!")

        # Test switching prompt on the card back bar
        print("5. Testing prompt switching directly on card back...")
        back_prompt_select = page.locator('#fcBackAiPromptSelect')
        assert await back_prompt_select.is_visible(), "Back prompt select should be visible"
        prompt_options = await back_prompt_select.locator('option').all_text_contents()
        print(f"Back prompt select options: {prompt_options}")
        # Select vocab prompt
        await back_prompt_select.select_option('vocab')
        await page.wait_for_timeout(300)
        vocab_content = await page.locator('#fcBackContent').inner_html()
        print('VOCAB CONTENT:', vocab_content[:200])
        assert "Vocabulary" in vocab_content or "Verdacht" in vocab_content, "Card back should update to show Vocabulary prompt content"
        print("✓ Prompt switched on card back to Vocabulary!")

        # Test keyboard shortcut 'T' to toggle back to Original
        print("6. Testing keyboard shortcut 'T' to revert/toggle card back view...")
        await page.keyboard.press('t')
        await page.wait_for_timeout(300)
        assert await orig_tab.evaluate("el => el.classList.contains('active')"), "'T' should toggle to Original tab"
        assert not await page.locator('#fcBackAiBar').is_visible(), "AI bar should be hidden in original view"
        print("✓ Reverted to original via 'T' shortcut")

        # Toggle 'T' again to return to AI view
        await page.keyboard.press('t')
        await page.wait_for_timeout(300)
        assert await ai_tab.evaluate("el => el.classList.contains('active')"), "'T' should toggle back to AI mode"
        print("✓ Swapped back to AI mode via 'T' shortcut")

        # Open AI Side Panel to test multi-version and prompt chips
        print("7. Opening AI Side Panel to verify Prompt Chips and Version Controls...")
        await page.locator('#fcAiToggleBtn').click()
        await page.wait_for_timeout(500)
        sidepanel = page.locator('#fcInfoSidePanel')
        assert not await sidepanel.evaluate("el => el.classList.contains('collapsed')"), "AI side panel should be open"

        # Verify Prompt Chips
        prompt_chips = page.locator('#fcInfoPromptChips')
        assert await prompt_chips.is_visible(), "Prompt chips bar should be visible"
        chips_text = await prompt_chips.locator('.fc-prompt-chip').all_text_contents()
        print(f"✓ Prompt chips visible on this card: {chips_text}")

        # Verify Swap to Back button in AI panel
        swap_back_btn = page.locator('#fcSwapBackBtn')
        assert await swap_back_btn.is_visible(), "Swap to Back button should be visible in action bar"
        swap_text = await swap_back_btn.text_content()
        print(f"Swap button text: {swap_text}")
        assert "Revert" in swap_text, "Swap button should indicate active state ('Revert Card Back')"

        # Switch to detailed prompt by clicking its chip
        print("8. Switching to 'Detailed' prompt chip...")
        await prompt_chips.locator('.fc-prompt-chip').first.click()
        await page.wait_for_timeout(500)

        # Test creating a new version
        print("9. Testing '➕ New Ver' button...")
        # Make sure api key is present in localStorage
        await page.evaluate("() => localStorage.setItem('mdv_openrouter_api_key', 'test-key-dummy')")
        await page.evaluate("() => { if (typeof aiSettings !== 'undefined') aiSettings.openrouter_api_key = 'test-key-dummy'; }")

        ver_select = page.locator('#fcVersionSelect')
        assert await ver_select.is_visible(), "Version select should be visible for prompt with output"
        initial_ver_count = len(await ver_select.locator('option').all())
        print(f"Initial versions count for Detailed prompt: {initial_ver_count}")
        assert initial_ver_count >= 1, "Should have at least 1 version for Detailed prompt"

        await page.locator('#fcNewVersionBtn').click()
        await page.wait_for_timeout(800)

        new_ver_options = await ver_select.locator('option').all_text_contents()
        print(f"Updated versions options: {new_ver_options}")
        assert len(new_ver_options) > initial_ver_count, "New version should be added to version select"
        assert any("v2" in opt or "(Latest)" in opt for opt in new_ver_options), "v2 should appear as Latest"
        print("✓ New version created and saved successfully!")

        # Verify card back automatically updated with the new version
        back_html = await page.locator('#fcBackContent').inner_html()
        assert "Enhanced AI Study Notes (v2)" in back_html or "v2" in back_html
        print("✓ Card back reflects new version in real time!")

        # Take screenshot of the multi-prompt, multi-version, swapped card back learning UI
        screenshot_path = '/home/dkchw/Distrobox/.gemini/antigravity-cli/brain/ea78fc3d-e39a-4ce0-8cc4-515668713d5f/scratch/fc_ai_multiversion_swap_showcase.png'
        await page.screenshot(path=screenshot_path)
        print(f"✓ Screenshot captured: {screenshot_path}")

        print("\nALL MULTI-PROMPT, MULTI-VERSION & SWAP E2E TESTS PASSED!")
        await browser.close()

asyncio.run(run())
