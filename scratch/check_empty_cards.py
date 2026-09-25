import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/home/dkchw/.nix-profile/bin/chromium', headless=True)
        page = await browser.new_page()
        await page.goto('http://127.0.0.1:2026/?file=Kontext/B1%2B/L01%20Mit%20der%20Zeit.md&mode=flashcard', wait_until='networkidle')
        await page.wait_for_timeout(2000)
        res = await page.evaluate('''() => {
            const list = window.getFlashcardList();
            const aiCards = window.getCurrentFileAiCards();
            return list.map((c, i) => {
                let orig = '';
                if (c.card_content !== undefined) orig = c.card_content;
                else if (typeof lines !== 'undefined' && lines) {
                    const s = c.line + 1;
                    const e = c.end;
                    if (s <= e) orig = lines.slice(s, e + 1).join('\\n');
                }
                const slug = c.slug || ('H' + c.level + '::' + (c.text||'').trim());
                const hasAi = aiCards.has(slug) || aiCards.has('H' + c.level + '::' + (c.text||'').trim());
                return { i, text: c.text, level: c.level, origLen: orig.trim().length, hasAi };
            });
        }''')
        empty = [x for x in res if x['origLen'] == 0]
        has_orig = [x for x in res if x['origLen'] > 0]
        no_ai = [x for x in res if not x['hasAi']]
        print(f"Total cards: {len(res)}")
        print(f"Empty orig cards: {len(empty)}")
        print(f"Cards with orig content: {len(has_orig)}")
        print(f"Cards without AI supplement: {len(no_ai)}, sample: {no_ai[:5]}")
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
