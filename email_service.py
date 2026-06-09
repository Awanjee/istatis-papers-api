"""Quote email delivery for iStatis.

Extracted verbatim from main.py (no behaviour change) so that
transport/templating concerns live apart from the HTTP layer.
Swap the body of send_quote_email later (e.g. for a templating
engine or a transactional provider) without touching routes.
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _build_quote_html(quote: dict, date_str: str) -> str:
    """Render the customer-facing quote email body."""
    quote_body = quote["quote_text"].replace(chr(10), "<br>")
    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;
        max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#1a472a;padding:20px;
            border-radius:8px;margin-bottom:24px;">
            <h1 style="color:white;margin:0;
                font-size:20px;">iStatis</h1>
            <p style="color:#a8d5b5;margin:4px 0 0;
                font-size:13px;">
                Quote &mdash; {date_str}
            </p>
        </div>
        <div style="padding:0 4px;color:#333;
            font-size:14px;line-height:1.6;">
            {quote_body}
        </div>
        <div style="margin-top:24px;padding:16px;
            background:#f0f7f4;border-radius:8px;
            font-size:13px;color:#555;">
            <strong>Quote Details:</strong><br>
            Product: {quote['product_name']}<br>
            Quantity: {quote['quantity']:,} units<br>
            {quote['pricing_summary']}
        </div>
        <div style="margin-top:16px;font-size:11px;
            color:#999;text-align:center;">
            iStatis &bull; Islamabad, Pakistan &bull;
            usamaawan925@gmail.com
        </div>
    </body>
    </html>
    """


def send_quote_email(quote: dict) -> bool:
    """Send quote email to the customer and notify iStatis.

    Returns True on success, False if credentials are missing or
    delivery fails. Never raises to the caller.
    """
    gmail = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not all([gmail, password]):
        return False

    date_str = datetime.now().strftime("%d %B %Y")
    html = _build_quote_html(quote, date_str)

    try:
        # Email to customer
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"Your Quote from iStatis — "
            f"{quote['product_name']} x "
            f"{quote['quantity']:,}"
        )
        msg["From"] = gmail
        msg["To"] = quote["email"]
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, password)
            server.sendmail(gmail, quote["email"], msg.as_string())

        # Notification to iStatis
        notify_msg = MIMEMultipart("alternative")
        notify_msg["Subject"] = (
            f"New Quote Request — "
            f"{quote['customer_name']} @ {quote['company']}"
        )
        notify_msg["From"] = gmail
        notify_msg["To"] = gmail
        notify_msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, password)
            server.sendmail(gmail, gmail, notify_msg.as_string())

        return True

    except Exception as e:
        print(f"Email error: {e}")
        return False
