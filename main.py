from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
import os
from extraction_router import router as extraction_router
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from agent import chat, generate_quote
from auth import get_current_user
from database import (
    create_order_from_quote,
    get_client_by_email,
    get_quotes_for_client,
)
from fastapi.middleware.cors import CORSMiddleware
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

app = FastAPI(title="Arco Papers AI Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(extraction_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Ensure CORS headers are present even on unhandled 500s."""
    import traceback
    traceback.print_exc()  # still logs to uvicorn terminal
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=CORS_HEADERS,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensure CORS headers are present on HTTPExceptions (4xx/5xx)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=CORS_HEADERS,
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
    product_name: str
    quantity: int
    notes: str = ""


class QuoteResponse(BaseModel):
    success: bool
    message: str
    quote_summary: str


class QuoteHistoryItem(BaseModel):
    id: str
    quantity: int
    unit_price: float
    total_price: float
    status: str
    notes: str | None = None
    created_at: str | None = None
    quote_text: str | None = None
    product_name: str | None = None
    product_unit: str | None = None


class OrderCreateRequest(BaseModel):
    quote_id: str


class OrderResponse(BaseModel):
    id: str
    status: str
    total_amount: float
    quote_id: str
    product_name: str | None = None
    message: str = "Order created successfully"


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
            Product: {quote['product_name']}<br>
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
            f"{quote['product_name']} x "
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
    print(f"Received request: {request}")
    try:
        quote = await generate_quote(
            customer_name=request.customer_name,
            company=request.company,
            email=request.email,
            product_name=request.product_name,
            quantity=request.quantity,
            notes=request.notes,
        )

        if "error" in quote:
            return QuoteResponse(
                success=False,
                message=quote["error"],
                quote_summary="",
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
            message=f"Error: {str(e)}",
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


def _quote_to_history_item(row: dict) -> QuoteHistoryItem:
    product = row.get("products") or {}
    return QuoteHistoryItem(
        id=row["id"],
        quantity=row["quantity"],
        unit_price=float(row["unit_price"]),
        total_price=float(row["total_price"]),
        status=row["status"],
        notes=row.get("notes"),
        created_at=row.get("created_at"),
        quote_text=row.get("quote_text"),
        product_name=product.get("name"),
        product_unit=product.get("unit"),
    )


@app.get("/quotes/history", response_model=list[QuoteHistoryItem])
async def quotes_history(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    rows = get_quotes_for_client(email)
    return [_quote_to_history_item(r) for r in rows]


@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    email = current_user["email"]
    client = get_client_by_email(email)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No client record found. Submit a quote first.",
        )

    try:
        order = create_order_from_quote(request.quote_id, client["id"])
    except ValueError as e:
        msg = str(e)
        if "does not belong" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return OrderResponse(
        id=order["id"],
        status=order["status"],
        total_amount=float(order["total_amount"]),
        quote_id=request.quote_id,
        product_name=order.get("product_name"),
    )
