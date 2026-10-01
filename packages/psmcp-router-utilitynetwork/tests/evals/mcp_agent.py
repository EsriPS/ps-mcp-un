"""Bare MCP-connected agent loop for the eval harness.

The agent is deliberately *unharnessed*: it receives only a minimal system
prompt telling it that it is an agent with a set of tools. All domain guidance
must come from the MCP server itself — tool docstrings, resources, and prompts.

The loop records every tool call, resource read, and prompt fetch so the scorer
can measure whether the agent discovered and followed the server's guidance.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client

logger = logging.getLogger(__name__)

_BARE_SYSTEM_PROMPT = (
    "You are an autonomous agent connected to a set of tools over MCP. "
    "You also have access to reference resources and guided prompts exposed by "
    "the server. Use the tools and any guidance you can discover to answer the "
    "user's question. When you have the final answer, state it plainly and stop."
)


@dataclass
class RunTrace:
    """Full record of a single agent run against one prompt."""

    prompt_id: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    resources_read: list[str] = field(default_factory=list)
    prompts_fetched: list[str] = field(default_factory=list)
    final_answer: str = ""
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize the trace to a JSON-safe dict (never includes secrets)."""
        return {
            "prompt_id": self.prompt_id,
            "tools_called": self.tools_called,
            "resources_read": self.resources_read,
            "prompts_fetched": self.prompts_fetched,
            "final_answer": self.final_answer,
            "error": self.error,
            "steps": self.steps,
        }


def _tool_to_openai_schema(tool: Any) -> dict[str, Any]:
    """Convert an MCP tool descriptor into an OpenAI tool-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


def _discovery_tools(resources: list[Any], prompts: list[Any]) -> list[dict[str, Any]]:
    """Expose resource-read and prompt-get as callable tools.

    A generic MCP client surfaces resources and prompts to the model as things
    it can pull. We model that here as two synthetic tools so a plain
    tool-calling LLM can choose to discover guidance on its own — which is
    exactly the behavior we want to measure.
    """
    resource_uris = [str(r.uri) for r in resources]
    prompt_names = [p.name for p in prompts]
    tools: list[dict[str, Any]] = []
    if resource_uris:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_resource",
                    "description": (
                        "Read a reference resource published by the server. "
                        f"Available URIs: {', '.join(resource_uris)}"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {"uri": {"type": "string", "enum": resource_uris}},
                        "required": ["uri"],
                    },
                },
            }
        )
    if prompt_names:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "get_prompt",
                    "description": (
                        "Fetch a guided prompt/playbook published by the server. "
                        f"Available names: {', '.join(prompt_names)}"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "enum": prompt_names}},
                        "required": ["name"],
                    },
                },
            }
        )
    return tools


async def run_prompt(
    *,
    client: Client,
    llm: Any,
    model: str,
    prompt_id: str,
    prompt_text: str,
    max_steps: int,
) -> RunTrace:
    """Run one unharnessed agent session for a single prompt.

    Args:
        client: An already-connected FastMCP client (fresh per run).
        llm: An OpenAI-compatible client exposing chat.completions.create.
        model: Model id to use.
        prompt_id: Identifier recorded in the trace.
        prompt_text: The user question.
        max_steps: Maximum tool-calling iterations before giving up.

    Returns:
        A populated :class:`RunTrace`.
    """
    trace = RunTrace(prompt_id=prompt_id)

    mcp_tools = await client.list_tools()
    resources = await client.list_resources()
    prompts = await client.list_prompts()

    tool_schemas = [_tool_to_openai_schema(t) for t in mcp_tools]
    tool_schemas.extend(_discovery_tools(resources, prompts))
    tool_names = {t["function"]["name"] for t in tool_schemas}

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _BARE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    for _step in range(max_steps):
        try:
            response = llm.chat.completions.create(
                model=model,
                messages=messages,
                tools=tool_schemas,
                temperature=0,
            )
        except Exception as exc:  # LLM call failure ends the run
            trace.error = f"llm_error: {exc}"
            logger.error("LLM call failed for %s: %s", prompt_id, exc)
            return trace

        choice = response.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            trace.final_answer = (msg.content or "").strip()
            trace.steps.append({"type": "final", "content": trace.final_answer})
            return trace

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            result_text = await _dispatch_tool(client, name, args, tool_names, trace)

            trace.steps.append({"type": "tool", "name": name, "args": args})
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result_text}
            )

    trace.error = "max_steps_exceeded"
    return trace


async def _dispatch_tool(
    client: Client,
    name: str,
    args: dict[str, Any],
    known_names: set[str],
    trace: RunTrace,
) -> str:
    """Route a tool call to the MCP server, recording discovery in the trace."""
    if name == "read_resource":
        uri = args.get("uri", "")
        trace.resources_read.append(uri)
        try:
            content = await client.read_resource(uri)
            return _stringify(content)
        except Exception as exc:
            return f"error reading resource {uri}: {exc}"

    if name == "get_prompt":
        pname = args.get("name", "")
        trace.prompts_fetched.append(pname)
        try:
            result = await client.get_prompt(pname)
            return _stringify(result)
        except Exception as exc:
            return f"error fetching prompt {pname}: {exc}"

    if name not in known_names:
        return f"unknown tool: {name}"

    trace.tools_called.append(name)
    try:
        result = await client.call_tool(name, args)
        return _stringify(result)
    except Exception as exc:
        return f"error calling {name}: {exc}"


def _stringify(result: Any) -> str:
    """Best-effort convert an MCP result into text for the model."""
    # fastmcp returns objects with .data / .content depending on version.
    data = getattr(result, "data", None)
    if data is not None:
        try:
            return json.dumps(data, default=str)
        except (TypeError, ValueError):
            return str(data)

    content = getattr(result, "content", None)
    if content is not None:
        parts: list[str] = []
        for block in content if isinstance(content, list) else [content]:
            text = getattr(block, "text", None)
            parts.append(text if text is not None else str(block))
        return "\n".join(parts)

    return str(result)
