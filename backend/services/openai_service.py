"""OpenAI service for streaming chat completions with thinking model support."""
from __future__ import annotations

import json
import logging
import platform
from datetime import datetime, timezone
import tiktoken
from openai import OpenAI
from config import Config
from tools.registry import tool_registry

_client: OpenAI | None = None
log = logging.getLogger(__name__)


def get_openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


_TOOL_TRANSPARENCY_FALLBACK = (
    "You have tools for memory, documents, accounting (QuickBooks/NetSuite via "
    "Merge.dev — list accounts, search transactions, create bills), "
    "Float (card transactions, account transactions, bill payments, "
    "reimbursements, users, cards), and Gmail (list, read, send, draft, reply, "
    "forward, and label messages). "
    "When a user asks about financial data, spend, transactions, emails, or "
    "anything that a tool can answer, ALWAYS call the appropriate tool — never "
    "guess or say data is unavailable without trying the tool first. "
    "After using a tool, tell the user which tool you used, summarise the data "
    "it returned, and state the source (from the `tool_used` and `source` fields "
    "in the response)."
)


_SKILLS_INSTRUCTION = (
    "## Skills\n"
    "Before replying, scan the skills list below. If exactly one skill "
    "clearly applies to the user's request, use the skill_read tool to "
    "read its full instructions, then follow them. If multiple could "
    "apply, choose the most specific one. If none clearly apply, proceed "
    "normally without reading any skill.\n\n"
)


def _build_runtime_context() -> str:
    """Build a runtime context block with date, time, and model info."""
    now = datetime.now(timezone.utc)
    return (
        f"[Runtime]\n"
        f"Date: {now.strftime('%A, %B %d, %Y')}\n"
        f"Time: {now.strftime('%H:%M')} UTC\n"
        f"OS: {platform.system()} {platform.release()}\n"
        f"Model: {Config.OPENAI_MODEL}"
    )


def build_messages(
    history: list[dict],
    memory_context: str | None = None,
    retrieved_context: str | None = None,
    history_hours: int | None = None,
    skills_context: str | None = None,
    bootstrap_context: str | None = None,
) -> list[dict]:
    """
    Convert DB message rows into the OpenAI messages format.

    Injection order (matching OpenClaw's prompt architecture):
    1. bootstrap_context — SOUL → IDENTITY → USER → AGENTS → TOOLS (→ BOOTSTRAP on first run)
    2. Tool transparency fallback (only when bootstrap is empty)
    3. Runtime context (date, time, OS, model)
    4. Skills list
    5. Memory context (today + yesterday daily logs)
    6. RAG-retrieved memories
    7. History window notice
    8. Conversation history
    """
    messages: list[dict] = []

    # 1. Bootstrap files (personality, identity, user, operating instructions, tools, onboarding)
    if bootstrap_context:
        messages.append({
            'role': 'system',
            'content': bootstrap_context,
        })
    else:
        # Fallback: if no bootstrap files exist yet, inject basic tool guidance
        messages.append({
            'role': 'system',
            'content': _TOOL_TRANSPARENCY_FALLBACK,
        })

    # 2. Runtime context
    messages.append({
        'role': 'system',
        'content': _build_runtime_context(),
    })

    # 3. Skills list so the agent can discover user-defined skills
    if skills_context:
        messages.append({
            'role': 'system',
            'content': _SKILLS_INSTRUCTION + skills_context,
        })

    # 4. Memory context (today + yesterday daily logs)
    if memory_context:
        messages.append({
            'role': 'system',
            'content': (
                "[Memory Context — recent daily notes]\n\n"
                + memory_context
            ),
        })

    # 5. RAG-retrieved memories
    if retrieved_context:
        messages.append({
            'role': 'system',
            'content': (
                "[Retrieved Memories — relevant past context]\n\n"
                + retrieved_context
            ),
        })

    # 6. History window notice
    if history_hours:
        messages.append({
            'role': 'system',
            'content': (
                f"Your conversation history below covers only the last {history_hours} hours. "
                "For anything older, rely on the Memory Context and Retrieved Memories above, "
                "or use the memory_search and memory_read tools."
            ),
        })

    for msg in history:
        role = msg['role']
        entry: dict = {'role': role}

        if role == 'tool':
            entry['content'] = msg.get('content', '')
            entry['tool_call_id'] = msg.get('tool_call_id', '')
        elif role == 'assistant' and msg.get('tool_calls'):
            entry['content'] = msg.get('content') or ''
            entry['tool_calls'] = msg['tool_calls']
        else:
            entry['content'] = msg.get('content', '')

        messages.append(entry)
    return messages


# ── Token counting ───────────────────────────────────────────────────

def count_tokens(messages: list[dict]) -> int:
    """
    Estimate the token count for a list of OpenAI messages.

    Uses tiktoken with a fallback to cl100k_base if the model encoding
    is not directly available.
    """
    try:
        enc = tiktoken.encoding_for_model(Config.OPENAI_MODEL)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    total = 0
    for msg in messages:
        # Every message has overhead tokens (~4 per message)
        total += 4
        for key, value in msg.items():
            if isinstance(value, str):
                total += len(enc.encode(value))
            elif isinstance(value, list):
                # tool_calls are stored as list of dicts
                total += len(enc.encode(json.dumps(value)))
    total += 2  # reply priming
    return total


# ── Pre-compaction flush (silent, non-streamed) ──────────────────────

_FLUSH_SYSTEM_PROMPT = (
    "The conversation is approaching the context window limit. "
    "Review the conversation and use the memory_append tool to save any "
    "important decisions, facts, user preferences, or context that should "
    "persist beyond this session. Use memory_save for anything that belongs "
    "in long-term memory (MEMORY.md). If there is nothing worth saving, "
    "do not call any tools."
)


def run_flush_completion(messages: list[dict]) -> list[dict] | None:
    """
    Run a non-streamed completion for the silent pre-compaction flush turn.

    Returns a list of tool_call dicts (OpenAI format) if the model wants
    to persist anything, or None if no tool calls are made.
    """
    client = get_openai()

    flush_messages = messages + [
        {"role": "system", "content": _FLUSH_SYSTEM_PROMPT},
    ]

    kwargs: dict = {
        "model": Config.OPENAI_MODEL,
        "messages": flush_messages,
    }

    if tool_registry.has_tools:
        kwargs["tools"] = tool_registry.to_openai_tools()

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        log.exception("flush_completion_failed")
        return None

    choice = response.choices[0] if response.choices else None
    if choice is None:
        return None

    if choice.message.tool_calls:
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    return None


def stream_chat(messages: list[dict]):
    """
    Generator that yields SSE-formatted events from an OpenAI streaming response.

    Event types:
      - thinking: reasoning/thinking content from the model
      - content: regular assistant content
      - tool_call: a tool call chunk
      - done: stream completed, includes final message data
      - error: an error occurred
    """
    client = get_openai()
    model = Config.OPENAI_MODEL

    kwargs: dict = {
        'model': model,
        'messages': messages,
        'stream': True,
    }

    # Add tools if any are registered
    if tool_registry.has_tools:
        kwargs['tools'] = tool_registry.to_openai_tools()

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        log.exception(
            "stream_chat_openai_failed model=%s has_tools=%s message_count=%s",
            model,
            tool_registry.has_tools,
            len(messages),
        )
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        return

    full_content = ""
    full_thinking = ""
    tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}

    try:
        for chunk in response:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta

            # Thinking content (reasoning tokens)
            if hasattr(delta, 'reasoning') and delta.reasoning:
                full_thinking += delta.reasoning
                yield f"event: thinking\ndata: {json.dumps({'content': delta.reasoning})}\n\n"

            # Regular content
            if delta.content:
                full_content += delta.content
                yield f"event: content\ndata: {json.dumps({'content': delta.content})}\n\n"

            # Tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            'id': tc.id or '',
                            'type': 'function',
                            'function': {'name': '', 'arguments': ''},
                        }
                    if tc.id:
                        tool_calls_acc[idx]['id'] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]['function']['name'] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]['function']['arguments'] += tc.function.arguments

                    yield f"event: tool_call\ndata: {json.dumps({'index': idx, 'tool_call': tool_calls_acc[idx]})}\n\n"

            # Check for finish
            if choice.finish_reason:
                break

    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        return

    # Build final tool_calls list (sorted by index)
    final_tool_calls = None
    if tool_calls_acc:
        final_tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]

    yield f"event: done\ndata: {json.dumps({'content': full_content, 'thinking': full_thinking, 'tool_calls': final_tool_calls})}\n\n"


def generate_title(user_message: str, assistant_message: str) -> str:
    """Generate a short conversation title from the first exchange."""
    client = get_openai()
    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MINI_MODEL,
            messages=[
                {
                    'role': 'system',
                    'content': 'Generate a short title (max 6 words) for a conversation that starts with the following exchange. Return only the title, no quotes or punctuation.',
                },
                {'role': 'user', 'content': user_message},
                {'role': 'assistant', 'content': assistant_message[:500]},
            ],
            max_completion_tokens=20,
        )
        title = response.choices[0].message.content.strip()
        return title[:100]  # Safety cap
    except Exception:
        log.exception("generate_title_failed")
        return 'New Chat'


# ── Document summarisation ───────────────────────────────────────────

_SUMMARIZE_PROMPT = (
    "You are a document analyst. The user has uploaded a file named \"{filename}\". "
    "Below is the extracted text content. Write a brief summary (3-5 sentences) that captures: "
    "the type of document, its main topics, key facts/numbers, and any notable details. "
    "This summary will be stored in the user's daily notes for future reference."
)

_SUMMARIZE_MAX_CHARS = 15_000  # ~4k tokens for the configured mini model


def summarize_document(text: str, filename: str) -> str | None:
    """
    Generate a brief summary of a document using the configured mini model.

    Returns None on failure so a summarisation error never blocks the upload.
    """
    client = get_openai()
    truncated = text[:_SUMMARIZE_MAX_CHARS]
    indicator = "\n\n[... document truncated ...]" if len(text) > _SUMMARIZE_MAX_CHARS else ""

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MINI_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARIZE_PROMPT.format(filename=filename)},
                {"role": "user", "content": truncated + indicator},
            ],
            max_completion_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        log.exception("summarize_document_failed filename=%s", filename)
        return None
