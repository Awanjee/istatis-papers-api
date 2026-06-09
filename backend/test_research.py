"""
Test script for the Research Assistant.

This script runs the agent and prints the FULL conversation trace so you can
see every decision the model made, every tool it called, and every result it
received. This is the best way to understand the agent loop in action.

Run from istatis-papers (uses istatis-papers/venv, not the parent .venv):
  cd C:\\Usama\\Projects\\istatis\\istatis-papers
  .\\venv\\Scripts\\Activate.ps1
  python backend\\test_research.py
"""

import json
import sys

from research_assistant import run_research_assistant


def _configure_console() -> None:
    """Avoid UnicodeEncodeError on Windows cp1252 consoles."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_configure_console()

# ─────────────────────────────────────────────────────────────────────────────
# The research task we're giving the agent.
# This is intentionally a meaty task so the model has to make multiple
# tool calls — you'll see the loop iterate several times.
# ─────────────────────────────────────────────────────────────────────────────
TASK = (
    "Research LangGraph vs LangChain for Python agent development "
    "and save a comparison note"
)

print("=" * 70)
print("RESEARCH ASSISTANT — FULL TRACE")
print("=" * 70)
print(f"\nTask: {TASK}\n")
print("Running agent... (this may take 30-60 seconds)\n")
print("-" * 70)

# Run the agent. It returns the final response and the trace log.
final_response, trace = run_research_assistant(TASK)

# ─────────────────────────────────────────────────────────────────────────────
# Print the full trace — every tool call the model made and every result.
# ─────────────────────────────────────────────────────────────────────────────

if not trace:
    print("No tool calls were made (model answered directly).\n")
else:
    print(f"The model made {len(trace)} tool call(s):\n")

    for i, entry in enumerate(trace, 1):
        print(f"{'=' * 70}")
        print(f"  TOOL CALL #{i}  (iteration {entry['iteration']})")
        print(f"{'=' * 70}")
        print(f"  Function : {entry['function']}")
        print(f"  Call ID  : {entry['tool_call_id']}")
        print()

        # Pretty-print the arguments the model chose.
        print("  Arguments:")
        args_str = json.dumps(entry["arguments"], indent=4)
        for line in args_str.splitlines():
            print(f"    {line}")
        print()

        # Print the result our Python function returned.
        print("  Result:")
        result_str = str(entry["result"])

        # If the result looks like JSON, pretty-print it.
        try:
            parsed = json.loads(result_str)
            result_str = json.dumps(parsed, indent=4)
        except (json.JSONDecodeError, TypeError):
            pass

        # Truncate very long results in the trace to keep output readable.
        MAX_RESULT_DISPLAY = 800
        if len(result_str) > MAX_RESULT_DISPLAY:
            result_str = result_str[:MAX_RESULT_DISPLAY] + "\n    [...result "
            "truncated "
            "for display...]"

        for line in result_str.splitlines():
            print(f"    {line}")
        print()

# ─────────────────────────────────────────────────────────────────────────────
# Print the final response the model gave after all tool calls.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("  FINAL RESPONSE FROM MODEL")
print("=" * 70)
print()
print(final_response)
print()
print("=" * 70)
print(f"  Done. {len(trace)} tool call(s) made across the agent loop.")
print("  Check backend/notes.json to see the saved note.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 4 ERROR RECOVERY TEST
# Deliberately feeds the agent a URL that will fail.
# Expected: fetch_and_summarise returns a "Failed to fetch..." error string,
# the model reads it, and recovers gracefully — no crash, no hang.
# ─────────────────────────────────────────────────────────────────────────────
print("\n\n" + "=" * 70)
print("  LEVEL 4 ERROR RECOVERY TEST — FAILING URL")
print("=" * 70)

ERROR_TASK = "Fetch this page and summarise it: " "https://httpstat.us/500"

print(f"\nTask: {ERROR_TASK}\n")
print("Running agent...\n")
print("-" * 70)

error_response, error_trace = run_research_assistant(ERROR_TASK)

if not error_trace:
    print("No tool calls made.\n")
else:
    print(f"The model made {len(error_trace)} tool call(s):\n")
    for i, entry in enumerate(error_trace, 1):
        print(f"  Tool #{i}: {entry['function']}")
        print(f"  Result : {str(entry['result'])[:300]}")
        print()

print("=" * 70)
print("  FINAL RESPONSE")
print("=" * 70)
print(error_response)
print()

# What to look for:
#   1. Result for fetch_and_summarise should start with "Failed to fetch"
#   2. Final response should acknowledge the failure gracefully
#   3. No Python exception — clean exit
passed = any(
    "Failed to fetch" in str(e["result"]) or "failed" in str(e["result"]).lower()
    for e in error_trace
)
print(
    f"Error caught and returned to model: {'PASS' if passed else 'FAIL — check trace'}"
)
print("=" * 70)
