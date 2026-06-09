"""
Research Assistant — LangGraph implementation (Level 5 + RAG)

Same capability as research_assistant.py (Level 4) but built as a LangGraph
graph instead of a hand-rolled while loop.  Adds a search_catalog tool that
does semantic search over the iStatis product catalog via ChromaDB.

Compare the two files side by side to see exactly what LangGraph buys you:
  - The agent loop is gone
  - Tool dispatch is gone
  - finish_reason checking is gone
  - The graph declaration replaces all of it

Prerequisites:
  Index the catalog first (one-time, costs a few cents in embeddings):
    cd C:\\Usama\\Projects\\istatis-papers
    venv\\Scripts\\python backend/rag.py

Run:
  cd C:\\Usama\\Projects\\istatis-papers
  venv\\Scripts\\python backend/research_assistant_lg.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Annotated

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from dotenv import load_dotenv

from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Make sure backend/ is importable when running as a script
sys.path.insert(0, str(Path(__file__).parent))
from rag import query_catalog  # noqa: E402

load_dotenv()

# ---------------------------------------------------------------------------
# Notes file — same location as Level 4 so both agents share the same notes
# ---------------------------------------------------------------------------
NOTES_FILE = Path(__file__).parent / "notes.json"

# ---------------------------------------------------------------------------
# Tools
# Decorated with @tool so LangGraph can inspect the signature and docstring
# to build the JSON schema automatically. No manual schema writing.
# ---------------------------------------------------------------------------


@tool
def search_web(query: str) -> str:
    """
    Search the web using DuckDuckGo and return the top 5 results.
    Use this to find current information on any topic.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return f"No results found for: {query}"

        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['href']}")
            lines.append(f"   {r['body']}\n")

        return "\n".join(lines)

    except Exception as e:
        return f"Search failed: {e}"


@tool
def fetch_and_summarise(url: str) -> str:
    """
    Fetch a web page and return its main text content.
    Use this when you need the full content of a specific page.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 40]
        content = "\n".join(lines[:80])

        return f"Content from {url}:\n\n{content}"

    except Exception as e:
        return f"Failed to fetch {url}: {e}"


@tool
def save_note(title: str, content: str) -> str:
    """
    Save a research note to notes.json for later retrieval.
    Use this to preserve findings the user will want to reference.
    """
    try:
        notes = []
        if NOTES_FILE.exists():
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                notes = json.load(f)

        note = {
            "id": len(notes) + 1,
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)

        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)

        return f"Note saved: \"{title}\" (ID: {note['id']})"

    except Exception as e:
        return f"Failed to save note: {e}"


@tool
def get_saved_notes() -> str:
    """
    Retrieve all previously saved research notes.
    Use this to check what has already been researched.
    """
    try:
        if not NOTES_FILE.exists():
            return "No notes saved yet."

        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            notes = json.load(f)

        if not notes:
            return "Notes file is empty."

        lines = []
        for note in notes:
            lines.append(f"--- Note #{note['id']}: {note['title']} ---")
            lines.append(f"Created: {note['created_at']}")
            lines.append(note["content"])
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to read notes: {e}"


@tool
def search_catalog(query: str) -> str:
    """
    Search the LOCAL iStatis product catalog (ChromaDB vector store).
    This catalog contains pricing tiers, product specs, minimum order quantities,
    lead times, custom printing details, and company information for all iStatis
    products: envelopes (C4, C5, DL, A4, courier, window), paper (A4/A3, 70/80gsm),
    stationery (letter pads, notebooks, registers), files/folders, and printing services.

    ALWAYS call this tool FIRST for any question about iStatis products, pricing,
    or services — it is faster and more accurate than web search for these topics.

    Args:
        query: a natural-language question about iStatis products or pricing
    """
    try:
        result = query_catalog(query, k=3)
        return result if result else "No matching catalog entries found."
    except Exception as e:
        return f"Catalog search failed: {e}"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

TOOLS = [search_web, fetch_and_summarise, save_note, get_saved_notes, search_catalog]


# State is just a list of messages with the add_messages reducer.
# add_messages appends new messages rather than replacing the list.
# This is the LangGraph equivalent of the messages list you managed manually.
class State(TypedDict):
    messages: Annotated[list, add_messages]


# Model with tools bound — replaces the TOOLS JSON schema list from Level 4.
# LangGraph reads the @tool decorators and builds the schemas automatically.
model = ChatOpenAI(model="gpt-4o").bind_tools(TOOLS)


def call_model(state: State) -> dict:
    """
    Node 1: send the current message history to the model and get a response.
    Returns the assistant message to be appended to state.
    """
    response = model.invoke(state["messages"])
    return {"messages": [response]}


# Node 2: ToolNode handles tool dispatch automatically.
# In Level 4 you wrote execute_tool() and the dispatch loop yourself.
# ToolNode replaces all of that.
tool_node = ToolNode(TOOLS)


def build_graph():
    graph = StateGraph(State)

    graph.add_node("call_model", call_model)
    # Name must be "tools" — tools_condition routes to that node id by default.
    graph.add_node("tools", tool_node)

    graph.set_entry_point("call_model")

    # tools_condition checks the last message:
    #   if it has tool_calls → route to tools
    #   otherwise → END
    # This replaces your finish_reason == "tool_calls" check.
    graph.add_conditional_edges("call_model", tools_condition)

    # After tools run, always go back to the model.
    graph.add_edge("tools", "call_model")

    return graph.compile()


# ---------------------------------------------------------------------------
# Runner — same interface as Level 4 for easy comparison
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a focused research assistant with access to the iStatis internal product catalog (via search_catalog) and the web (via search_web).

CRITICAL RULE: For ANY question about iStatis products, pricing, envelopes, paper, stationery, files, printing services, or company info — call search_catalog FIRST before doing anything else. This catalog is the authoritative source and will always have the answer.

Workflow:
1. iStatis product/pricing question? → search_catalog immediately
2. External or current web info needed? → search_web
3. Need full page content? → fetch_and_summarise
4. Check for prior research? → get_saved_notes
5. Preserve key findings? → save_note
6. Summarise clearly once you have enough information.

Be thorough but efficient. Aim to complete research in 3-5 tool calls."""


def run_research_assistant(task: str) -> str:
    """
    Run the LangGraph research agent on a task.
    Returns the final response string.

    Note: no trace return here — LangGraph's state contains the full
    message history which is richer than the manual trace from Level 4.
    """
    app = build_graph()

    initial_state = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=task),
        ]
    }

    # stream_mode="values" yields the full state after each node runs.
    # This is how you observe the graph executing step by step.
    final_state = None
    for state in app.stream(initial_state, stream_mode="values"):
        final_state = state

    # The last message in state is the final assistant response.
    last_message = final_state["messages"][-1]
    return last_message.content


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # RAG smoke-test: single focused query — should be answered entirely from
    # the local ChromaDB catalog without a single web search call.
    task = (
        "What are the bulk pricing tiers for C4 envelopes at iStatis, "
        "and what is the minimum order quantity?"
    )

    print("=" * 70)
    print("RESEARCH ASSISTANT (LangGraph + RAG) — Level 5")
    print("=" * 70)
    print(f"\nTask: {task}\n")
    print("Running...\n")

    result = run_research_assistant(task)

    print("=" * 70)
    print("FINAL RESPONSE")
    print("=" * 70)
    print(result)
    print("=" * 70)
