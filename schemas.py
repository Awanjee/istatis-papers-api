"""Pydantic request/response models for the iStatis API.

Extracted from main.py so route handlers and schemas can grow
independently. Import these in main.py (same package, flat layout):

    from schemas import MessageRequest, QuoteRequest, ...
"""

from pydantic import BaseModel


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
