from typing import Any

from dotenv import load_dotenv

try:
    # Imported for typing + history storage. We keep these optional so the
    # module can import even if langchain isn't installed yet.
    from langchain_core.messages import AIMessage, HumanMessage  # type: ignore
    from langchain_core.messages import BaseMessage  # type: ignore
except Exception:  # pragma: no cover
    AIMessage = HumanMessage = BaseMessage = Any  # type: ignore

try:
    # `@tool` decorator. Optional at import time.
    from langchain_core.tools import tool  # type: ignore
except Exception:  # pragma: no cover

    def tool(fn):  # type: ignore
        return fn


load_dotenv()

# ── Product documents ───────────────────────────────────────
PRODUCT_DOCS = [
    """Arco Papers - Envelopes:
    C4 Envelope (229x324mm): PKR 10/unit (1000+), PKR 7/unit (5000+),
    PKR 6/unit (10000+). Min order 1000.
    C5 Envelope (162x229mm): PKR 6.5/unit (1000+), PKR 4.5/unit (5000+).
    Min order 1000.
    DL Envelope (110x220mm): PKR 5/unit (2000+), PKR 3.5/unit (10000+).
    Min order 2000.
    Custom printing available on all envelopes.""",
    """Arco Papers - Paper:
    A4 70gsm Ream (500 sheets): PKR 850/ream (10+), PKR 750/ream (100+),
    PKR 700/ream (500+).
    A4 80gsm Ream (500 sheets): PKR 1000/ream (10+), PKR 850/ream (100+),
    PKR 800/ream (500+).
    A3 80gsm Ream (500 sheets): PKR 1900/ream. Min order 5 reams.""",
    """Arco Papers - File Carriers:
    A4 Standard File Carrier: PKR 45/unit (100+), PKR 35/unit (500+),
    PKR 30/unit (1000+).
    A4 Heavy Duty File Carrier: PKR 70/unit (100+), PKR 55/unit (500+).
    Popular with hospitals and government.
    A3 File Carrier: PKR 90/unit. Min order 50 units.""",
    """Arco Papers - Company:
    Manufacturer and supplier in Islamabad, Rawalpindi and Lahore, Pakistan.
    Clients include Islamabad Diagnostic Center and Allama Iqbal University.
    Experience with government and NGO tenders. Custom orders available.
    Delivery across Pakistan for bulk orders. B2B bank transfer payments.""",
]

# ── Pricing tiers ───────────────────────────────────────────
PRICING = {
    "envelope_c4": [(10000, 6.0), (5000, 7.0), (1000, 10.0), (0, 12.0)],
    "envelope_c5": [(5000, 4.5), (1000, 6.5), (0, 8.0)],
    "envelope_dl": [(10000, 3.5), (2000, 5.0), (0, 6.0)],
    "paper_a4_70gsm": [(500, 700.0), (100, 750.0), (10, 850.0), (0, 900.0)],
    "paper_a4_80gsm": [(500, 800.0), (100, 850.0), (10, 1000.0), (0, 1050.0)],
    "file_carrier_standard": [(1000, 30.0), (500, 35.0), (100, 45.0), (0, 50.0)],
    "file_carrier_heavy": [(500, 55.0), (100, 70.0), (0, 75.0)],
}


def build_vectorstore():
    # Lazy imports so `agent.py` can be imported without LangChain installed.
    from langchain_chroma import Chroma  # type: ignore
    from langchain_openai import OpenAIEmbeddings  # type: ignore
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.create_documents(PRODUCT_DOCS)
    return Chroma.from_documents(
        chunks,
        embeddings,
    )
    # No persist_directory — stays in memory


@tool
def get_pricing_tier(product_type: str, quantity: int) -> str:
    """Get correct price per unit based on product type and quantity ordered.
    Use for any pricing or cost question."""
    if product_type not in PRICING:
        return f"Unknown product. Available: {list(PRICING.keys())}"
    for min_qty, price in PRICING[product_type]:
        if quantity >= min_qty:
            total = price * quantity
            return (
                f"{product_type} x {quantity:,} units = PKR {price}/unit | "
                f"Total: PKR {total:,.0f}"
            )
    return "Quantity too low for this product."


@tool
def calculate_order_cost(
    unit_price_pkr: float, quantity: int, discount_pct: float = 0
) -> str:
    """Calculate total order cost. Use when customer needs a final quote."""
    subtotal = unit_price_pkr * quantity
    discount = subtotal * (discount_pct / 100)
    total = subtotal - discount
    return (
        f"Subtotal: PKR {subtotal:,.0f} | Discount: PKR {discount:,.0f} | "
        f"Total: PKR {total:,.0f}"
    )


def build_agent():
    """
    Build the LangChain-based agent.

    Note: LangChain has had frequent breaking API moves. This function is kept
    separate and is called lazily so the FastAPI app can start even if the
    LangChain stack isn't available yet.
    """

    from langchain_openai import ChatOpenAI  # type: ignore
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    tools: list[Any] = [get_pricing_tier, calculate_order_cost]

    # Optional: add a lightweight product search tool if vectorstore deps exist.
    try:
        vectorstore = build_vectorstore()

        @tool  # type: ignore[misc]
        def search_products(query: str) -> str:
            """Search Arco Papers catalogue for product info/specs/company details."""
            q = (query or "").strip()
            if not q:
                return "Please provide a search query."
            results = vectorstore.similarity_search(q, k=2)
            if not results:
                return "No results found."
            return "\n\n".join(getattr(d, "page_content", str(d)) for d in results)

        tools = [search_products, get_pricing_tier, calculate_order_cost]
    except Exception:
        pass

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a professional sales assistant for Arco Papers,
        a paper manufacturer in Islamabad, Pakistan. Be concise and helpful.
        Always use tools for pricing. Quote prices in PKR only.
        If unsure, say you will check and follow up.""",
            ),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    # LangChain's agent helpers have moved across versions.
    # - Older/newer installs may not expose `create_tool_calling_agent`.
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent

        agent = create_tool_calling_agent(llm, tools, prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            max_iterations=5,
        )
    except Exception:
        from langchain_core.messages import SystemMessage  # type: ignore
        from langgraph.prebuilt import create_react_agent  # type: ignore

        system_prompt = (
            "You are a professional sales assistant for Arco Papers, "
            "a paper manufacturer in Islamabad, Pakistan. Be concise and helpful. "
            "Always use tools for pricing. Quote prices in PKR only. "
            "If unsure, say you will check and follow up."
        )

        graph = create_react_agent(
            llm,
            tools,
            prompt=system_prompt,
            version="v2",
        )

        class _GraphExecutor:
            def __init__(self, compiled_graph: Any):
                self._graph = compiled_graph

            def invoke(self, inputs: dict) -> dict:
                user_input = (inputs or {}).get("input", "")
                history_messages = (inputs or {}).get("history", []) or []
                state = {
                    "messages": [SystemMessage(content=system_prompt)]
                    + list(history_messages)
                    + [HumanMessage(content=str(user_input))],
                }
                out = self._graph.invoke(state)
                messages = out.get("messages", []) if isinstance(out, dict) else []
                last = messages[-1] if messages else None
                content = getattr(last, "content", None)
                return {"output": str(content) if content is not None else str(out)}

        return _GraphExecutor(graph)


_executor: Any | None = None
_executor_error: str | None = None


def _get_executor() -> Any | None:
    global _executor, _executor_error
    if _executor is not None or _executor_error is not None:
        return _executor
    try:
        _executor = build_agent()
    except Exception as e:  # pragma: no cover
        _executor_error = str(e)
        _executor = None
    return _executor


def _fallback_chat(message: str) -> str:
    msg = (message or "").strip()
    if not msg:
        return "Please type your question."

    lower = msg.lower()
    if "price" in lower or "cost" in lower or "quote" in lower:
        return (
            "Tell me the product type and quantity, e.g. "
            "`envelope_c4 5000` or `paper_a4_80gsm 100`."
        )

    return (
        "I’m running in fallback mode (LangChain agent not available yet). "
        "Ask me for pricing like: `envelope_c5 1000`."
    )


def chat(message: str, history: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
    executor = _get_executor()

    if executor is None:
        answer = _fallback_chat(message)
        history.append(HumanMessage(content=message))
        history.append(AIMessage(content=answer))
        return answer, history

    # AgentExecutor has `.invoke(...)` returning {"output": "..."}.
    # Runnable agents may return different shapes; handle both.
    response = executor.invoke({"input": message, "history": history})
    answer = response["output"] if isinstance(response, dict) else str(response)
    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=answer))
    return answer, history
