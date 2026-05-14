from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool

try:
    from langchain_classic.agents import (
        create_tool_calling_agent,
        AgentExecutor,
    )
except ImportError:
    from langchain_core.agents import (
        create_tool_calling_agent,
    )
    from langchain.agents import AgentExecutor
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)
from langchain_chroma import Chroma
from langchain_core.tools.retriever import (
    create_retriever_tool,
)
from dotenv import load_dotenv
from database import (
    get_products_with_pricing,
    get_pricing_for_product,
    save_quote,
)

load_dotenv()


def build_product_docs() -> list[str]:
    """
    Build RAG documents dynamically from
    the database instead of hardcoded strings.
    """
    products = get_products_with_pricing()
    docs = []

    # Group by category
    categories: dict[str, list] = {}
    for p in products:
        cat = p["categories"]["name"]
        categories.setdefault(cat, []).append(p)

    for cat_name, cat_products in categories.items():
        lines = [f"Arco Papers - {cat_name}:"]
        for p in cat_products:
            tiers = sorted(
                p["pricing_tiers"],
                key=lambda x: x["min_quantity"],
                reverse=True,
            )
            tier_str = ", ".join(
                f"PKR {t['price_per_unit']}/unit " f"({t['label']})" for t in tiers
            )
            lines.append(
                f"{p['name']}: {tier_str}. "
                f"Min order {p['min_order']}. "
                f"{p['description']}"
            )
        docs.append("\n".join(lines))

    # Company info doc
    docs.append(
        "Arco Papers - Company Information:\n"
        "Manufacturer and supplier of envelopes, "
        "paper, file carriers, registers and "
        "notebooks in Islamabad, Rawalpindi and "
        "Lahore, Pakistan.\n"
        "Major clients include Islamabad Diagnostic "
        "Center and Allama Iqbal University.\n"
        "Experience with government and NGO tenders "
        "including army and US-AID.\n"
        "Custom printing available on envelopes.\n"
        "Delivery available across Pakistan for "
        "bulk orders.\n"
        "B2B bank transfer payments accepted."
    )

    return docs


def build_vectorstore():
    """Build vector store from database products."""
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    docs = build_product_docs()
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.create_documents(docs)
    return Chroma.from_documents(chunks, embeddings)


# ── Tools ────────────────────────────────────────────────


@tool
def get_pricing_tier(
    product_name: str,
    quantity: int,
) -> str:
    """
    Get the correct price per unit for a product
    based on quantity. Use for any pricing question.
    product_name: name of the product e.g.
    'C4 Envelope', 'A4 Paper 70gsm'
    quantity: number of units requested
    """
    result = get_pricing_for_product(product_name, quantity)

    if not result:
        return (
            f"Product '{product_name}' not found. "
            "Please check the product catalogue."
        )

    return (
        f"{result['product_name']} x "
        f"{result['quantity']:,} {result['unit']} "
        f"= PKR {result['price_per_unit']} per unit "
        f"(tier: {result['tier_label']}) | "
        f"Total: PKR {result['total']:,.0f}"
    )


@tool
def calculate_order_cost(
    unit_price_pkr: float,
    quantity: int,
    discount_pct: float = 0,
) -> str:
    """
    Calculate total order cost with optional
    discount. Use when customer needs a final quote.
    """
    subtotal = unit_price_pkr * quantity
    discount = subtotal * (discount_pct / 100)
    total = subtotal - discount
    return (
        f"Subtotal: PKR {subtotal:,.0f} | "
        f"Discount: PKR {discount:,.0f} | "
        f"Total: PKR {total:,.0f}"
    )


def build_agent():
    vectorstore = build_vectorstore()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    retriever_tool = create_retriever_tool(
        vectorstore.as_retriever(search_kwargs={"k": 2}),
        name="search_products",
        description=(
            "Search Arco Papers product catalogue "
            "for product info, specs, pricing, "
            "and company details."
        ),
    )

    tools = [
        retriever_tool,
        get_pricing_tier,
        calculate_order_cost,
    ]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a professional sales assistant "
                "for Arco Papers, a paper manufacturer "
                "in Islamabad, Pakistan. Be concise and "
                "helpful. Always use tools for pricing. "
                "Quote prices in PKR only. "
                "If unsure, say you will check and "
                "follow up.",
            ),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=5,
    )


executor = build_agent()


def chat(
    message: str,
    history: list,
) -> tuple[str, list]:
    response = executor.invoke({"input": message, "history": history})
    answer = response["output"]
    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=answer))
    return answer, history


async def generate_quote(
    customer_name: str,
    company: str,
    email: str,
    product_name: str,
    quantity: int,
    notes: str = "",
) -> dict:
    """
    Generate a professional quote and save
    to the database.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    # Get pricing from database
    pricing = get_pricing_for_product(product_name, quantity)

    if not pricing:
        return {"error": (f"Product '{product_name}' " "not found in catalogue.")}

    pricing_summary = (
        f"{pricing['product_name']} x "
        f"{pricing['quantity']:,} units = "
        f"PKR {pricing['price_per_unit']}/unit | "
        f"Total: PKR {pricing['total']:,.0f}"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a professional sales "
                "representative for Arco Papers, a "
                "paper manufacturer in Islamabad, "
                "Pakistan. Generate a formal but "
                "friendly quote email body. Include: "
                "thank the customer by name, confirm "
                "product and quantity, state pricing "
                "clearly in PKR, mention delivery is "
                "available across Pakistan, ask them "
                "to reply to confirm the order, sign "
                "off as Arco Papers Sales Team. "
                "Keep it under 150 words.",
            ),
            (
                "human",
                "Customer: {name}\n"
                "Company: {company}\n"
                "Product: {product}\n"
                "Quantity: {quantity}\n"
                "Pricing: {pricing}\n"
                "Notes: {notes}",
            ),
        ]
    )

    chain = prompt | llm | StrOutputParser()

    quote_text = await chain.ainvoke(
        {
            "name": customer_name,
            "company": company,
            "product": pricing["product_name"],
            "quantity": f"{quantity:,}",
            "pricing": pricing_summary,
            "notes": notes or "None",
        }
    )

    # Save to database
    saved = save_quote(
        client_name=customer_name,
        company=company,
        email=email,
        product_id=pricing["product_id"],
        quantity=quantity,
        unit_price=float(pricing["price_per_unit"]),
        total_price=float(pricing["total"]),
        quote_text=quote_text,
        notes=notes,
    )

    return {
        "quote_text": quote_text,
        "pricing_summary": pricing_summary,
        "customer_name": customer_name,
        "company": company,
        "email": email,
        "product_name": pricing["product_name"],
        "quantity": quantity,
        "quote_id": saved["id"],
    }
