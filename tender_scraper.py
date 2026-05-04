import asyncio
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from playwright.async_api import async_playwright
import os
import json

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── KEYWORDS for relevance filtering ───────────────────────
# Edit these to match your products
KEYWORDS = [
    "envelope",
    "envelopes",
    "stationery",
    "paper",
    "file carrier",
    "file folders",
    "registers",
    "notebooks",
    "office supplies",
    "printing",
    "packaging",
    "letterhead",
]


# ── SCRAPER FUNCTIONS ───────────────────────────────────────


async def scrape_ppra() -> list[dict]:
    """Scrape PPRA EPADS active tenders."""
    tenders = []
    url = "https://epms.ppra.gov.pk/public/tenders/" "active-tenders"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            logger.info("Scraping PPRA EPADS...")
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(4000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "html.parser")

        # Try table rows first
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2:
                title = cells[0].get_text(strip=True)
                org = cells[1].get_text(strip=True) if len(cells) > 1 else "N/A"
                date = cells[2].get_text(strip=True) if len(cells) > 2 else "N/A"
                if title and len(title) > 10:
                    tenders.append(
                        {
                            "title": title,
                            "organization": org,
                            "date": date,
                            "source": "PPRA EPADS",
                            "url": url,
                        }
                    )

        # Fallback — grab any links with tender text
        if not tenders:
            links = soup.find_all("a", href=True)
            for link in links:
                text = link.get_text(strip=True)
                if len(text) > 20:
                    tenders.append(
                        {
                            "title": text[:200],
                            "organization": "PPRA",
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "source": "PPRA EPADS",
                            "url": url,
                        }
                    )

        logger.info(f"PPRA EPADS: found {len(tenders)} tenders")

    except Exception as e:
        logger.error(f"PPRA scraping failed: {e}")

    return tenders


async def scrape_pakpost() -> list[dict]:
    """Scrape Pakistan Post active tenders — free source."""
    tenders = []
    url = "https://www.pakpost.gov.pk/active_tenders.php"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            logger.info("Scraping Pakistan Post...")
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(3000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "html.parser")

        # Pakistan Post uses anchor links for tenders
        links = soup.find_all("a", href=True)
        for link in links:
            text = link.get_text(strip=True)
            if len(text) > 20 and any(
                kw in text.lower()
                for kw in ["tender", "supply", "purchase", "procurement", "stationery"]
            ):
                tenders.append(
                    {
                        "title": text[:200],
                        "organization": "Pakistan Post",
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "source": "Pakistan Post",
                        "url": url,
                    }
                )

        logger.info(f"Pakistan Post: found {len(tenders)} tenders")

    except Exception as e:
        logger.error(f"Pakistan Post scraping failed: {e}")

    return tenders


async def scrape_tenderservice() -> list[dict]:
    """
    Scrape TenderServicePakistan stationery category.
    Free preview available without subscription.
    """
    tenders = []
    url = "https://tenderservicepakistan.com" "/Tender/category/Stationery"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            logger.info("Scraping TenderServicePakistan...")
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(4000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "html.parser")

        # Get all text blocks that look like tender titles
        candidates = soup.find_all(["td", "div", "li", "p"])
        seen = set()
        for el in candidates:
            text = el.get_text(strip=True)
            if (
                len(text) > 30
                and text not in seen
                and any(
                    kw in text.lower()
                    for kw in [
                        "stationery",
                        "paper",
                        "envelope",
                        "supply",
                        "procurement",
                        "purchase",
                        "notebook",
                        "register",
                        "printing",
                    ]
                )
            ):
                seen.add(text)
                tenders.append(
                    {
                        "title": text[:200],
                        "organization": "See listing",
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "source": "TenderService.pk",
                        "url": url,
                    }
                )

        logger.info(f"TenderService: found {len(tenders)} tenders")

    except Exception as e:
        logger.error(f"TenderService scraping failed: {e}")

    return tenders


# ── KEYWORD PRE-FILTER ──────────────────────────────────────


def keyword_filter(tenders: list[dict]) -> list[dict]:
    """
    Fast pre-filter before hitting the LLM.
    Only passes tenders containing at least one keyword.
    Saves API costs.
    """
    filtered = []
    for tender in tenders:
        text = tender["title"].lower()
        if any(kw.lower() in text for kw in KEYWORDS):
            filtered.append(tender)

    logger.info(f"Keyword filter: {len(tenders)} → {len(filtered)}")
    return filtered


# ── LLM SCORING ─────────────────────────────────────────────


async def score_tenders(
    tenders: list[dict],
) -> list[dict]:
    """
    Use LLM to score each tender 0-100 for relevance
    to Arco Papers. Returns tenders with score added.
    """
    if not tenders:
        return []

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    parser = StrOutputParser()

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a procurement analyst for 
        Arco Papers, a supplier of envelopes, paper, 
        file carriers, registers and notebooks in Pakistan.
        
        Score the following tender 0-100 for relevance:
        - 80-100: Direct match (envelopes, paper, stationery)
        - 60-79: Partial match (office supplies, printing)
        - 40-59: Weak match (packaging, related items)
        - 0-39: Not relevant
        
        Respond ONLY with valid JSON in this exact format:
        {{"score": 85, "reason": "Direct envelope tender"}}
        
        No other text. Just the JSON.""",
            ),
            ("human", "Tender: {title}\nOrg: {organization}"),
        ]
    )

    chain = prompt | llm | parser
    scored = []

    for tender in tenders:
        try:
            result = await chain.ainvoke(
                {
                    "title": tender["title"],
                    "organization": tender["organization"],
                }
            )

            # Strip markdown fences if present
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1]
                clean = clean.rsplit("```", 1)[0]

            parsed = json.loads(clean)
            tender["score"] = parsed.get("score", 0)
            tender["reason"] = parsed.get("reason", "No reason given")

            if tender["score"] >= 60:
                scored.append(tender)
                logger.info(f"Score {tender['score']}: " f"{tender['title'][:50]}")

        except Exception as e:
            logger.error(f"Scoring failed for tender: {e}")
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Scored {len(scored)} relevant tenders")
    return scored


# ── EMAIL DIGEST ────────────────────────────────────────────


def send_digest(tenders: list[dict]) -> None:
    """Send HTML email digest via Gmail."""

    gmail = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    notify = os.getenv("NOTIFY_EMAIL")

    if not all([gmail, password, notify]):
        logger.error("Email credentials missing in .env")
        return

    date_str = datetime.now().strftime("%d %B %Y")
    high = [t for t in tenders if t["score"] >= 80]
    medium = [t for t in tenders if 60 <= t["score"] < 80]

    def score_badge(score: int) -> str:
        if score >= 80:
            color = "#2d6a4f"
            label = "High Match"
        elif score >= 60:
            color = "#e76f51"
            label = "Possible Match"
        else:
            color = "#999"
            label = "Weak Match"
        return (
            f'<span style="background:{color};'
            f"color:white;padding:3px 10px;"
            f"border-radius:12px;font-size:11px;"
            f'font-weight:600;">'
            f"{score} — {label}</span>"
        )

    def render_tender(t: dict) -> str:
        title = t["title"][:120]
        if len(t["title"]) > 120:
            title += "..."
        return f"""
        <tr>
            <td style="padding:16px;border-bottom:
                1px solid #f0f0f0;">
                <div style="margin-bottom:6px;">
                    {score_badge(t['score'])}
                    <span style="color:#999;
                        font-size:11px;
                        margin-left:8px;">
                        {t['source']} •
                        {t['date']}
                    </span>
                </div>
                <div style="font-size:14px;
                    font-weight:600;
                    color:#1a1a1a;
                    line-height:1.4;
                    margin-bottom:4px;">
                    {title}
                </div>
                <div style="font-size:12px;
                    color:#666;
                    margin-bottom:6px;">
                    {t['organization']}
                </div>
                <div style="font-size:12px;
                    color:#888;
                    font-style:italic;">
                    {t['reason']}
                </div>
            </td>
        </tr>
        """

    # ── Summary section ─────────────────────────────────
    summary_html = f"""
    <table width="100%" cellpadding="0"
        cellspacing="0"
        style="margin-bottom:24px;">
        <tr>
            <td width="33%" style="text-align:center;
                padding:16px;
                background:#f9f9f9;
                border-radius:8px;">
                <div style="font-size:28px;
                    font-weight:700;
                    color:#1a472a;">
                    {len(tenders)}
                </div>
                <div style="font-size:12px;
                    color:#666;margin-top:2px;">
                    Total Found
                </div>
            </td>
            <td width="4%"></td>
            <td width="33%" style="text-align:center;
                padding:16px;
                background:#f0f7f4;
                border-radius:8px;">
                <div style="font-size:28px;
                    font-weight:700;
                    color:#2d6a4f;">
                    {len(high)}
                </div>
                <div style="font-size:12px;
                    color:#666;margin-top:2px;">
                    High Match
                </div>
            </td>
            <td width="4%"></td>
            <td width="33%" style="text-align:center;
                padding:16px;
                background:#fff4f0;
                border-radius:8px;">
                <div style="font-size:28px;
                    font-weight:700;
                    color:#e76f51;">
                    {len(medium)}
                </div>
                <div style="font-size:12px;
                    color:#666;margin-top:2px;">
                    Possible Match
                </div>
            </td>
        </tr>
    </table>
    """

    # ── Tender rows ──────────────────────────────────────
    if tenders:
        rows_html = "".join(render_tender(t) for t in tenders)
        tender_section = f"""
        <table width="100%" cellpadding="0"
            cellspacing="0"
            style="border:1px solid #e0e0e0;
                border-radius:8px;
                overflow:hidden;">
            {rows_html}
        </table>
        """
        subject_line = (
            f"Arco Papers — {len(tenders)} Tender(s)"
            f" | {len(high)} High Match | {date_str}"
        )
    else:
        tender_section = """
        <div style="text-align:center;
            padding:40px;
            color:#999;
            background:#f9f9f9;
            border-radius:8px;">
            <div style="font-size:32px;
                margin-bottom:8px;">📭</div>
            <div style="font-size:14px;">
                No relevant tenders found this week.
            </div>
            <div style="font-size:12px;
                margin-top:4px;">
                Check again next Monday.
            </div>
        </div>
        """
        subject_line = f"Arco Papers — No Tenders This Week" f" | {date_str}"

    # ── Full email ───────────────────────────────────────
    html = f"""
    <html>
    <body style="margin:0;padding:0;
        background:#f5f5f5;
        font-family:Arial,sans-serif;">
        <table width="100%" cellpadding="0"
            cellspacing="0"
            style="background:#f5f5f5;
                padding:20px 0;">
            <tr>
                <td align="center">
                <table width="600" cellpadding="0"
                    cellspacing="0"
                    style="max-width:600px;
                        width:100%;
                        background:white;
                        border-radius:12px;
                        overflow:hidden;
                        box-shadow:0 2px 8px
                            rgba(0,0,0,0.08);">

                    <!-- Header -->
                    <tr>
                        <td style="background:#1a472a;
                            padding:24px;">
                            <div style="color:white;
                                font-size:20px;
                                font-weight:700;">
                                Arco Papers
                            </div>
                            <div style="color:#a8d5b5;
                                font-size:13px;
                                margin-top:4px;">
                                Weekly Tender Digest
                                — {date_str}
                            </div>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="padding:24px;">
                            {summary_html}
                            <div style="font-size:13px;
                                font-weight:600;
                                color:#333;
                                margin-bottom:12px;
                                text-transform:uppercase;
                                letter-spacing:0.5px;">
                                Tender Results
                            </div>
                            {tender_section}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding:16px 24px;
                            border-top:1px solid #eee;
                            background:#fafafa;">
                            <div style="font-size:11px;
                                color:#999;
                                text-align:center;">
                                Arco Papers Tender
                                Alert System •
                                Islamabad, Pakistan
                                • Runs every Monday
                                8am PKT
                            </div>
                        </td>
                    </tr>

                </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject_line
        msg["From"] = gmail
        msg["To"] = notify
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, password)
            server.sendmail(gmail, notify, msg.as_string())

        logger.info(f"Digest sent to {notify}")

    except Exception as e:
        logger.error(f"Email failed: {e}")


# ── MAIN PIPELINE ───────────────────────────────────────────


async def run_scraper() -> None:
    """Full pipeline: scrape → filter → score → email."""
    logger.info("Starting tender scraper pipeline...")

    # Scrape all three sources concurrently
    ppra, pakpost, tenderservice = await asyncio.gather(
        scrape_ppra(),
        scrape_pakpost(),
        scrape_tenderservice(),
    )

    all_tenders = ppra + pakpost + tenderservice
    logger.info(f"Total raw tenders: {len(all_tenders)}")

    if not all_tenders:
        logger.warning("No tenders scraped — check sites")
        send_digest([])
        return

    filtered = keyword_filter(all_tenders)

    if not filtered:
        logger.info("No keyword matches found")
        send_digest([])
        return

    scored = await score_tenders(filtered)
    send_digest(scored)
    logger.info("Pipeline complete.")


# ── SCHEDULER ───────────────────────────────────────────────


async def main():
    """
    Run once immediately, then schedule weekly.
    Every Monday at 8am Pakistan time (UTC+5).
    """
    print("Arco Papers Tender Scraper")
    print("=" * 40)
    print("Running now...")
    await run_scraper()

    # Schedule weekly
    scheduler = AsyncIOScheduler(timezone="Asia/Karachi")
    scheduler.add_job(
        run_scraper,
        "cron",
        day_of_week="mon",
        hour=8,
        minute=0,
    )
    scheduler.start()
    print("\nScheduler running — Monday 8am PKT")
    print("Press Ctrl+C to stop")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
