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


def get_quotes_for_client(
    email: str,
) -> list[dict]:
    """Get all quotes for a client by email."""
    result = (
        supabase.table("quotes")
        .select(
            "id, quantity, unit_price, "
            "total_price, status, notes, "
            "created_at, quote_text, "
            "products(name, unit)"
        )
        .eq("clients.email", email)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


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
