from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(url, key)


def get_tenant_id() -> str:
    """Get Arco Papers tenant ID."""
    result = (
        supabase.table("tenants")
        .select("id")
        .eq("name", "Arco Papers")
        .single()
        .execute()
    )
    return result.data["id"]


def get_products_with_pricing() -> list[dict]:
    """
    Fetch all active products with their
    pricing tiers and category names.
    """
    result = (
        supabase.table("products")
        .select(
            "id, name, description, unit, "
            "min_order, "
            "categories(name), "
            "pricing_tiers("
            "min_quantity, price_per_unit, label"
            ")"
        )
        .eq("is_active", True)
        .execute()
    )
    return result.data


def get_product_by_id(product_id: str) -> dict:
    """Fetch a single product with pricing tiers."""
    result = (
        supabase.table("products")
        .select(
            "id, name, description, unit, "
            "min_order, "
            "categories(name), "
            "pricing_tiers("
            "min_quantity, price_per_unit, label"
            ")"
        )
        .eq("id", product_id)
        .single()
        .execute()
    )
    return result.data


def get_pricing_for_product(
    product_name: str,
    quantity: int,
) -> dict | None:
    """
    Get applicable price for a product
    and quantity. Returns the correct tier.
    """
    result = (
        supabase.table("products")
        .select(
            "id, name, unit, "
            "pricing_tiers("
            "min_quantity, price_per_unit, label"
            ")"
        )
        .ilike("name", f"%{product_name}%")
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    product = result.data[0]
    tiers = sorted(
        product["pricing_tiers"],
        key=lambda x: x["min_quantity"],
        reverse=True,
    )

    applicable_price = None
    for tier in tiers:
        if quantity >= tier["min_quantity"]:
            applicable_price = tier["price_per_unit"]
            applicable_label = tier["label"]
            break

    if not applicable_price:
        return None

    return {
        "product_name": product["name"],
        "product_id": product["id"],
        "quantity": quantity,
        "unit": product["unit"],
        "price_per_unit": applicable_price,
        "tier_label": applicable_label,
        "total": applicable_price * quantity,
    }


def save_quote(
    client_name: str,
    company: str,
    email: str,
    product_id: str,
    quantity: int,
    unit_price: float,
    total_price: float,
    quote_text: str,
    notes: str = "",
) -> dict:
    """Save a quote to the database."""
    tenant_id = get_tenant_id()

    # Upsert client — create if not exists
    client_result = (
        supabase.table("clients")
        .upsert(
            {
                "tenant_id": tenant_id,
                "name": client_name,
                "company": company,
                "email": email,
            },
            on_conflict="email",
        )
        .execute()
    )
    client_id = client_result.data[0]["id"]

    # Save quote
    quote_result = (
        supabase.table("quotes")
        .insert(
            {
                "tenant_id": tenant_id,
                "client_id": client_id,
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "quote_text": quote_text,
                "notes": notes,
                "status": "sent",
            }
        )
        .execute()
    )

    return quote_result.data[0]


def get_client_by_email(email: str) -> dict | None:
    """Find a client row by email for the Arco Papers tenant."""
    tenant_id = get_tenant_id()
    result = (
        supabase.table("clients")
        .select("id, name, company, email")
        .eq("tenant_id", tenant_id)
        .eq("email", email)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def get_quotes_for_client_id(client_id: str) -> list[dict]:
    """Get all quotes for a client."""
    result = (
        supabase.table("quotes")
        .select(
            "id, client_id, product_id, quantity, unit_price, "
            "total_price, status, notes, "
            "created_at, quote_text, "
            "products(name, unit)"
        )
        .eq("client_id", client_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_quotes_for_client(email: str) -> list[dict]:
    """Get all quotes for a client by email."""
    client = get_client_by_email(email)
    if not client:
        return []
    return get_quotes_for_client_id(client["id"])


def get_quote_by_id(quote_id: str) -> dict | None:
    """Fetch a single quote with client_id for ownership checks."""
    result = (
        supabase.table("quotes")
        .select(
            "id, tenant_id, client_id, product_id, quantity, "
            "unit_price, total_price, status, notes, "
            "created_at, quote_text, "
            "products(name, unit)"
        )
        .eq("id", quote_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def create_order_from_quote(quote_id: str, client_id: str) -> dict:
    """
    Create an order and line item from an existing quote.
    Raises ValueError with a message for business-rule failures.
    """
    quote = get_quote_by_id(quote_id)
    if not quote:
        raise ValueError("Quote not found")

    if quote["client_id"] != client_id:
        raise ValueError("Quote does not belong to this client")

    if quote.get("status") in ("ordered", "cancelled"):
        raise ValueError(f"Quote cannot be ordered (status: {quote['status']})")

    tenant_id = quote["tenant_id"]
    total_amount = float(quote["total_price"])

    order_payload: dict = {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "quote_id": quote_id,
        "total_amount": total_amount,
        "status": "pending",
    }

    # quote_id column may exist on orders — include if present in schema
    order_result = supabase.table("orders").insert(order_payload).execute()
    order = order_result.data[0]
    order_id = order["id"]

    item_payload = {
        "order_id": order_id,
        "product_id": quote["product_id"],
        "quantity": quote["quantity"],
        "unit_price": float(quote["unit_price"]),
    }
    supabase.table("order_items").insert(item_payload).execute()

    supabase.table("quotes").update({"status": "ordered"}).eq("id", quote_id).execute()

    return {
        **order,
        "quote_id": quote_id,
        "product_name": quote.get("products", {}).get("name"),
    }


def get_dashboard_metrics() -> dict:
    """
    Basic metrics for the admin dashboard.
    """
    tenant_id = get_tenant_id()

    # Total quotes
    quotes = (
        supabase.table("quotes")
        .select("id, total_price, status")
        .eq("tenant_id", tenant_id)
        .execute()
    )

    # Total clients
    clients = (
        supabase.table("clients").select("id").eq("tenant_id", tenant_id).execute()
    )

    # Total orders
    orders = (
        supabase.table("orders")
        .select("id, total_amount, status")
        .eq("tenant_id", tenant_id)
        .execute()
    )

    total_quotes = len(quotes.data)
    total_clients = len(clients.data)
    total_orders = len(orders.data)
    total_revenue = sum(
        o["total_amount"] for o in orders.data if o["status"] != "cancelled"
    )
    pending_quotes = sum(1 for q in quotes.data if q["status"] == "pending")

    return {
        "total_quotes": total_quotes,
        "total_clients": total_clients,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "pending_quotes": pending_quotes,
    }
