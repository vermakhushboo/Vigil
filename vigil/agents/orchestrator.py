"""Vigil — Mistral Orchestrator Agent (via NVIDIA API).

Uses Mistral function calling to autonomously investigate incidents.
The agent iteratively calls tools (logs, commits, runbooks, past incidents)
until it has enough context to brief an engineer.

Uses NVIDIA's OpenAI-compatible API endpoint to access Mistral models.
"""
import json
import logging
from typing import Callable, Awaitable, Optional

from openai import AsyncOpenAI

from vigil.config import settings, get_async_llm_client, MODEL_LARGE
from vigil.models.incident import Incident, IncidentFindings
from vigil.tools.log_analyser import search_logs
from vigil.tools.github_finder import get_recent_commits
from vigil.tools.runbook_search import search_runbooks
from vigil.tools.incident_search import search_past_incidents

logger = logging.getLogger("vigil.agents.orchestrator")

# ─── System Prompt ───
SYSTEM_PROMPT = """You are Vigil, an autonomous incident response agent.
When given an incident, you must investigate it thoroughly before briefing the on-call engineer.
You have access to tools: search_logs, get_recent_commits, search_runbooks, search_past_incidents.

Call tools iteratively until you have identified:
1. The root cause or most likely cause
2. When it started
3. Any recent changes (deploys/commits) that may have caused it
4. A relevant runbook or past resolution

Only stop investigating when you have enough context to brief an engineer confidently.
Be concise. Engineers are asleep.

When you have completed your investigation, respond with a JSON summary in this exact format:
{
    "root_cause": "The most likely root cause",
    "started_at": "When the issue started",
    "last_commit": "The most suspicious recent commit (if any)",
    "runbook_match": "Key remediation steps from matching runbook",
    "past_similar": "Summary of similar past incidents and how they were resolved",
    "is_recurring": true/false,
    "recurrence_count": 0
}
"""

# ─── Tool Definitions for Mistral ───
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search Elasticsearch for recent error logs. Use this to find what errors are occurring and when they started.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms e.g. 'ERROR 500 exception' or 'database connection refused'",
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Time range e.g. '5m', '15m', '1h'",
                        "default": "10m",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_commits",
            "description": "Get the most recent Git commits to find if a bad deploy caused the incident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of commits to return",
                        "default": 5,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_runbooks",
            "description": "Search internal runbooks for remediation steps matching this incident type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Incident description to match against runbooks",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_past_incidents",
            "description": "Search historical incidents to find similar past events and how they were resolved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Incident description to find similar past incidents",
                    }
                },
                "required": ["query"],
            },
        },
    },
]

# ─── Tool dispatch map ───
TOOL_FUNCTIONS = {
    "search_logs": search_logs,
    "get_recent_commits": get_recent_commits,
    "search_runbooks": search_runbooks,
    "search_past_incidents": search_past_incidents,
}

MAX_ITERATIONS = 8  # Safety limit on agent loops


# Type alias for the event callback
EventCallback = Optional[Callable[[str, dict], Awaitable[None]]]


async def investigate(incident: Incident, on_event: EventCallback = None) -> IncidentFindings:
    """
    Run the Mistral orchestrator agent to investigate an incident.

    Args:
        incident: The incident to investigate.
        on_event: Optional async callback(event_type, data) for real-time UI updates.

    Returns:
        IncidentFindings with the investigation results.
    """
    async def _emit(event_type: str, data: dict = None):
        if on_event:
            try:
                await on_event(event_type, data or {})
            except Exception:
                pass  # Never let UI events break investigation

    if not settings.mistral_api_key:
        logger.error("❌ MISTRAL_API_KEY not set — cannot investigate")
        return IncidentFindings(
            root_cause="Investigation failed: MISTRAL_API_KEY not configured"
        )

    client = get_async_llm_client()

    # Build initial message with incident context
    incident_context = (
        f"INCIDENT ALERT:\n"
        f"- Title: {incident.title}\n"
        f"- Severity: {incident.severity}\n"
        f"- Service: {incident.service}\n"
        f"- Time: {incident.created_at.isoformat()}Z\n"
    )

    if incident.raw_alert:
        annotations = incident.raw_alert.get("annotations", {})
        description = annotations.get("description", "")
        if description:
            incident_context += f"- Description: {description}\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": incident_context + "\nPlease investigate this incident."},
    ]

    logger.info(f"🤖 Starting investigation for incident [{incident.id}]: {incident.title}")

    # ─── Agent Loop ───
    for iteration in range(MAX_ITERATIONS):
        logger.info(f"🔄 Agent iteration {iteration + 1}/{MAX_ITERATIONS}")

        try:
            response = await client.chat.completions.create(
                model=MODEL_LARGE,
                messages=messages,
                tools=TOOLS,
            )
        except Exception as e:
            logger.error(f"❌ Mistral API call failed: {e}")
            return IncidentFindings(root_cause=f"Investigation failed: Mistral API error - {e}")

        choice = response.choices[0]
        message = choice.message

        # Case 1: Mistral wants to call tools
        if message.tool_calls:
            # Serialize assistant message to dict for safe re-submission
            assistant_msg = {"role": "assistant", "content": message.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments if isinstance(tc.function.arguments, str) else json.dumps(tc.function.arguments),
                    },
                }
                for tc in message.tool_calls
            ]
            messages.append(assistant_msg)

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args_str = tool_call.function.arguments

                logger.info(f"🔧 Agent calling tool: {func_name}({func_args_str})")
                await _emit("tool_called", {"tool": func_name, "args": func_args_str, "iteration": iteration + 1})

                # Parse arguments
                try:
                    func_args = json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                except json.JSONDecodeError:
                    func_args = {}

                # Execute the tool
                tool_func = TOOL_FUNCTIONS.get(func_name)
                if tool_func:
                    try:
                        result = tool_func(**func_args)
                    except Exception as e:
                        result = f"Tool '{func_name}' failed: {e}"
                        logger.error(f"❌ Tool {func_name} failed: {e}")
                else:
                    result = f"Unknown tool: {func_name}"

                logger.info(f"📎 Tool result ({func_name}): {str(result)[:200]}...")
                await _emit("tool_result", {"tool": func_name, "result": str(result)[:500]})

                # Append tool result to messages
                messages.append({
                    "role": "tool",
                    "name": func_name,
                    "content": str(result),
                    "tool_call_id": tool_call.id,
                })

        # Case 2: Mistral returns text (investigation complete)
        elif message.content:
            logger.info(f"✅ Agent completed investigation after {iteration + 1} iterations")
            return _parse_findings(message.content)

        # Case 3: Unexpected — stop
        else:
            logger.warning("⚠️ Agent returned empty response, stopping")
            break

    logger.warning(f"⚠️ Agent hit max iterations ({MAX_ITERATIONS})")
    # Try to get a final answer
    messages.append({
        "role": "user",
        "content": "Please provide your investigation summary now as JSON, with what you've found so far.",
    })

    try:
        response = await client.chat.completions.create(
            model=MODEL_LARGE,
            messages=messages,
        )
        return _parse_findings(response.choices[0].message.content or "")
    except Exception:
        return IncidentFindings(root_cause="Investigation timed out after max iterations")


def _to_str(value) -> str | None:
    """Coerce a value to string — handles dicts/lists from LLM responses."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2)
    return str(value)


def _parse_findings(text: str) -> IncidentFindings:
    """Parse the agent's text response into IncidentFindings."""
    logger.info("📝 Parsing findings from agent response")

    # Try to extract JSON from the response
    try:
        # Look for JSON block in the text
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = text[json_start:json_end]
            data = json.loads(json_str)
            return IncidentFindings(
                root_cause=_to_str(data.get("root_cause")),
                started_at=_to_str(data.get("started_at")),
                last_commit=_to_str(data.get("last_commit")),
                runbook_match=_to_str(data.get("runbook_match")),
                past_similar=_to_str(data.get("past_similar")),
                is_recurring=bool(data.get("is_recurring", False)),
                recurrence_count=int(data.get("recurrence_count", 0)),
            )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Could not parse JSON from agent response: {e}")

    # Fallback: use the full text as root cause
    return IncidentFindings(root_cause=text[:500])
