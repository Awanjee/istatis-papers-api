from fastapi import FastAPI
from datetime import datetime
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from agent import chat, generate_quote
from fastapi.middleware.cors import CORSMiddleware
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = FastAPI(title="Arco Papers AI Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (our HTML frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory session store — simple dict keyed by session_id
# In production this would be Redis or a database
sessions: dict = {}


class MessageRequest(BaseModel):
    message: str
    session_id: str = "default"


class MessageResponse(BaseModel):
    response: str
    session_id: str


class QuoteRequest(BaseModel):
    customer_name: str
    company: str
    email: str
    product_type: str
    quantity: int
    notes: str = ""


class QuoteResponse(BaseModel):
    success: bool
    message: str
    quote_summary: str


def send_quote_email(quote: dict) -> bool:
    """Send quote email to customer and Arco Papers."""
    gmail = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not all([gmail, password]):
        return False

    date_str = datetime.now().strftime("%d %B %Y")

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;
        max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#1a472a;padding:20px;
            border-radius:8px;margin-bottom:24px;">
            <h1 style="color:white;margin:0;
                font-size:20px;">Arco Papers</h1>
            <p style="color:#a8d5b5;margin:4px 0 0;
                font-size:13px;">
                Quote — {date_str}
            </p>
        </div>
        <div style="padding:0 4px;color:#333;
            font-size:14px;line-height:1.6;">
            {quote['quote_text'].replace(
                chr(10), '<br>'
            )}
        </div>
        <div style="margin-top:24px;padding:16px;
            background:#f0f7f4;border-radius:8px;
            font-size:13px;color:#555;">
            <strong>Quote Details:</strong><br>
            Product: {quote['product_type']}<br>
            Quantity: {quote['quantity']:,} units<br>
            {quote['pricing_summary']}
        </div>
        <div style="margin-top:16px;font-size:11px;
            color:#999;text-align:center;">
            Arco Papers • Islamabad, Pakistan •
            usamaawan925@gmail.com
        </div>
    </body>
    </html>
    """

    try:
        # Email to customer
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"Your Quote from Arco Papers — "
            f"{quote['product_type']} x "
            f"{quote['quantity']:,}"
        )
        msg["From"] = gmail
        msg["To"] = quote["email"]
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, password)
            server.sendmail(gmail, quote["email"], msg.as_string())

        # Notification to Arco Papers
        notify_msg = MIMEMultipart("alternative")
        notify_msg["Subject"] = (
            f"New Quote Request — " f"{quote['customer_name']} " f"@ {quote['company']}"
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


@app.post("/quote", response_model=QuoteResponse)
async def quote_endpoint(request: QuoteRequest):
    try:
        quote = await generate_quote(
            customer_name=request.customer_name,
            company=request.company,
            email=request.email,
            product_type=request.product_type,
            quantity=request.quantity,
            notes=request.notes,
        )

        email_sent = send_quote_email(quote)

        return QuoteResponse(
            success=True,
            message=(
                "Quote sent to your email!"
                if email_sent
                else "Quote generated successfully."
            ),
            quote_summary=quote["pricing_summary"],
        )

    except Exception as e:
        return QuoteResponse(
            success=False,
            message=f"Error generating quote: {str(e)}",
            quote_summary="",
        )


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/chat", response_model=MessageResponse)
async def chat_endpoint(request: MessageRequest):
    # Get or create session history
    if request.session_id not in sessions:
        sessions[request.session_id] = []

    history = sessions[request.session_id]
    answer, updated_history = chat(request.message, history)
    sessions[request.session_id] = updated_history

    return MessageResponse(response=answer, session_id=request.session_id)


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(sessions)}
