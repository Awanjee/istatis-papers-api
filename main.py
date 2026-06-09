from dotenv import load_dotenv
load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from extraction_router import router as extraction_router
from fastapi.staticfiles import StaticFiles
from agent import chat, generate_quote
from auth import get_current_user
from database import (
    create_order_from_quote,
    get_client_by_email,
    get_quotes_for_client,
)
from fastapi.middleware.cors import CORSMiddleware
from email_service import send_quote_email
from schemas import (
    MessageRequest,
    MessageResponse,
    OrderCreateRequest,
    OrderResponse,
    QuoteHistoryItem,
    QuoteRequest,
    QuoteResponse,
)

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

app = FastAPI(title="iStatis AI Assistant")
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
