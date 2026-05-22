"""
Research Assistant — OpenAI Function Calling (Tool Use) Tutorial
================================================================
This module teaches you how OpenAI function calling works by building
a real research assistant. Read the comments top-to-bottom; they explain
every concept as you hit it.

HOW FUNCTION CALLING WORKS (the core idea):
  1. You define "tools" — JSON schemas describing functions the model CAN call.
  2. You send a message to the model along with those tool definitions.
  3. The model decides whether to answer directly OR to ask you to run a tool.
  4. If it wants a tool, it returns finish_reason="tool_calls" and tells you:
       - which function to call
       - what arguments to pass (as a JSON string)
  5. YOU execute the function — the model never runs code itself.
  6. You send the result back to the model as a "tool" role message.
  7. The model reads the result and either calls another tool or gives a
     final answer.
  8. Repeat steps 2–7 until finish_reason != "tool_calls". That's the
     agent loop.

Run this file:
  cd backend
  python test_research.py
"""

import json
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI

# find_dotenv() walks up from the current directory until it finds a .env file.
# This means we can run from inside /backend and still load /arco-papers/.env.
load_dotenv(find_dotenv())

# The OpenAI client reads OPENAI_API_KEY from the environment automatically.
client = OpenAI()

# Where we store saved notes — next to this script in the backend/ folder.
NOTES_FILE = Path(__file__).parent / "notes.json"


# =============================================================================
# TOOL IMPLEMENTATIONS
# These are normal Python functions. The model will ask us to call them;
# we execute them and return the result as a plain string.
# =============================================================================


def search_web(query: str) -> str:
    """
    Search DuckDuckGo and return top 5 results.
    Returns a JSON string so the model can parse structured data.
    """
    # ddgs provides a simple wrapper around DuckDuckGo's search.
    # DDGS() is a context manager that manages the HTTP session.
    # (The package was formerly called duckduckgo_search; now it's ddgs.)
    from ddgs import DDGS

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(
                    {
                        "title": r["title"],
                        "url": r["href"],
                        "snippet": r["body"],
                    }
                )

        if not results:
            return "No results found for that query."

        # Return as JSON string — the model reads this in the next turn.
        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Search failed: {e}"


def fetch_and_summarise(url: str) -> str:
    """
    Fetch a webpage, strip HTML tags, and return plain text (truncated).
    We truncate to 3000 chars so we don't blow up the model's context.
    The model will summarise it — we just provide the raw content.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (research-assistant/1.0)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # BeautifulSoup parses the HTML tree.
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style blocks — they're noise, not content.
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # get_text() extracts visible text; separator="\n" preserves structure.
        text = soup.get_text(separator="\n")

        # Collapse excessive whitespace/blank lines.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        # Truncate — 3000 chars is enough for the model to understand content.
        if len(clean_text) > 3000:
            clean_text = clean_text[:3000] + "\n\n[...content truncated...]"

        return clean_text

    except Exception as e:
        return f"Failed to fetch {url}: {e}"


def save_note(title: str, content: str) -> str:
    """
    Append a note to notes.json.
    We read existing notes, append the new one, then write back.
    This is safe for small note collections (no database needed for a demo).
    """
    try:
        # Load existing notes (or start fresh if the file doesn't exist yet).
        if NOTES_FILE.exists():
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                notes = json.load(f)
        else:
            notes = []

        # Each note gets a timestamp so we know when it was created.
        note = {
            "id": len(notes) + 1,
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat(),
        }

        notes.append(note)

        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)

        return f"Note saved successfully: \"{title}\" (ID: {note['id']})"

    except Exception as e:
        return f"Failed to save note: {e}"


def get_saved_notes() -> str:
    """
    Read and return all notes from notes.json as a formatted string.
    """
    try:
        if not NOTES_FILE.exists():
            return "No notes saved yet."

        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            notes = json.load(f)

        if not notes:
            return "Notes file is empty."

        # Format as readable text so the model can reference specific notes.
        lines = []
        for note in notes:
            lines.append(f"--- Note #{note['id']}: {note['title']} ---")
            lines.append(f"Created: {note['created_at']}")
            lines.append(note["content"])
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to read notes: {e}"


# =============================================================================
# TOOL DEFINITIONS (the JSON schemas the model reads)
#
# This is what you send to OpenAI in the "tools" parameter.
# The model reads these schemas to understand what functions are available
# and what arguments each function expects. It NEVER sees your Python code —
# only these JSON descriptions.
# =============================================================================

TOOLS = [
    {
        "type": "function",  # Always "function" for function calling.
        "function": {
            # Must match the Python function name exactly
            "name": "search_web",
            # (we use it as a key to dispatch calls below).
            "description": (
                "Search the web using DuckDuckGo. Use this to find current "
                "information, articles, and resources about any topic. "
                "Returns titles, URLs, and snippets for the top 5 results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "DuckDuckGo search query.",
                    }
                },
                "required": ["query"],  # The model MUST provide this argument.
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_and_summarise",
            "description": (
                "Fetch the content of a webpage and return its plain text. "
                "Use this after search_web when you need the full content of "
                "a specific article or page, not just the snippet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the webpage to fetch.",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": (
                "Save a research note to local storage. Use this to save "
                "summaries, findings, or any information worth keeping. "
                "Notes persist between sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short descriptive title for the note.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content/body of the note.",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_saved_notes",
            "description": (
                "Retrieve all previously saved research notes. Use this to "
                "review what has already been researched and saved."
            ),
            "parameters": {
                "type": "object",
                "properties": {},  # No arguments needed.
                "required": [],
            },
        },
    },
]


# =============================================================================
# TOOL DISPATCHER
#
# When the model requests a tool call, it gives us a function name (string)
# and arguments (JSON string). We need to route that to the right Python
# function and call it with the right arguments.
# =============================================================================

# A registry mapping function name → Python callable.
# This is simpler and safer than using eval() or getattr().
TOOL_REGISTRY = {
    "search_web": search_web,
    "fetch_and_summarise": fetch_and_summarise,
    "save_note": save_note,
    "get_saved_notes": get_saved_notes,
}


def execute_tool(tool_call) -> str:
    """
    Execute a single tool call requested by the model.

    tool_call is an object from the API response with:
      - tool_call.id          → unique ID we must echo back in the tool result
      - tool_call.function.name       → which function to call
      - tool_call.function.arguments  → JSON string of arguments
    """
    func_name = tool_call.function.name

    if func_name not in TOOL_REGISTRY:
        return f"Error: unknown function '{func_name}'"

    # Parse arguments — model may return malformed JSON under load.
    try:
        func_args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as e:
        return f"Error: could not parse arguments for '{func_name}': {e}"

    # Call the Python function with the model's arguments unpacked.
    return TOOL_REGISTRY[func_name](**func_args)


# =============================================================================
# THE AGENT LOOP
#
# This is the heart of function calling. It's a loop that:
#   1. Sends messages to the model
#   2. Checks if the model wants to run a tool
#   3. Runs the tool and appends the result to the message history
#   4. Sends the updated history back to the model
#   5. Repeats until the model gives a plain text answer
# =============================================================================


def run_research_assistant(user_message: str) -> tuple[str, list[dict]]:
    """
    Run the research assistant agent on a user message.

    Returns:
      - final_response: the model's last text answer
      - trace: a list of dicts recording every tool call and result,
               useful for understanding what the agent did
    """

    # ── Step 1: Build the initial message history ──────────────────────────
    # The system prompt tells the model who it is and when to use tools.
    messages = [
        {
            "role": "system",
            "content": (
                "You are a research assistant. When the user asks you to "
                "research a topic, use your tools to search the web, fetch "
                "relevant pages, and save findings as notes. Always save a "
                "summary note at the end. Be thorough — use multiple searches "
                "if needed."
            ),
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    # Record every tool call + result for test output.
    trace = []
    iteration = 0  # Safety counter to prevent infinite loops in case of bugs.
    max_iterations = 10

    # ── Step 2: The agent loop ─────────────────────────────────────────────
    while iteration < max_iterations:
        iteration += 1

        # Send message history + tool definitions to the model.
        # tool_choice="auto" means the model decides when
        # to use tools vs. answer directly.
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            return f"API call failed on iteration {iteration}: {e}", trace

        # The model's reply is in choices[0].message.
        # finish_reason tells us WHY the model stopped generating:
        #   "stop"       → normal end, the model gave a final text answer
        #   "tool_calls" → the model wants to run one or more tools
        #   "length"     → hit token limit (rare with short responses)
        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # ── Step 3: Check if the model wants to call tools ───────────────────
        if finish_reason == "tool_calls":
            # Tool call requests instead of a text answer.
            # message.tool_calls is a list — parallel tool calling supported.

            # IMPORTANT: We must append the assistant's message (including its
            # tool_calls list) to the history BEFORE appending tool results.
            # The model needs this context to understand what it asked for.
            messages.append(message)

            # ── Step 4: Execute each requested tool call ─────────────────────
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args_raw = tool_call.function.arguments  # JSON string

                # Run the actual Python function.
                try:
                    result = execute_tool(tool_call)
                except Exception as e:
                    result = f"Tool failed: {str(e)}. " "Consider "
                    " a different approach."

                # Record in trace for the test output.
                trace.append(
                    {
                        "iteration": iteration,
                        "tool_call_id": tool_call.id,
                        "function": func_name,
                        "arguments": json.loads(func_args_raw),
                        "result": result,
                    }
                )

                # ── Step 5: Append tool result to message history ────────────
                # Role "tool" returns function results to the model.
                # tool_call_id must match the ID from the tool call above.
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,  # Echo back the same ID.
                        "content": result,  # The function's return value.
                    }
                )

            # ── Step 6: Loop back — send updated history to the model
            # The model will now see its own tool requests AND the results,
            # and decide whether to call more tools or give a final answer.
            continue

        else:
            # ── Step 7: finish_reason is "stop" — final answer ───────────────
            # The model finished without requesting any tools.
            final_response = message.content or ""
            return final_response, trace

    # If we somehow hit max_iterations, return what we have.
    return "Max iterations reached without a final response.", trace
