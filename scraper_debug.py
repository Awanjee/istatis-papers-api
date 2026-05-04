import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


async def debug_sites():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # ── Debug PPRA ──────────────────────────────────────
        print("\n=== PPRA ===")
        page = await browser.new_page()
        await page.goto(
            "https://www.ppra.org.pk/dad_psrpt.asp" "?page=1&pg_no=1&secid=25",
            timeout=30000,
        )
        await page.wait_for_timeout(3000)
        content = await page.content()

        soup = BeautifulSoup(content, "html.parser")
        # Print first 2000 chars to see structure
        print(soup.get_text()[:2000])
        print("\n--- PPRA Tables found:", len(soup.find_all("table")))
        print("--- PPRA Rows found:", len(soup.find_all("tr")))

        # ── Debug PaperPK ───────────────────────────────────
        print("\n=== PAPERPK ===")
        page2 = await browser.new_page()
        await page2.goto("https://www.paperpk.com/tenders/stationery", timeout=30000)
        await page2.wait_for_timeout(3000)
        content2 = await page2.content()

        soup2 = BeautifulSoup(content2, "html.parser")
        print(soup2.get_text()[:2000])
        print("\n--- PaperPK Divs found:", len(soup2.find_all("div")))
        print("--- PaperPK Links found:", len(soup2.find_all("a")))

        await browser.close()


asyncio.run(debug_sites())
