"""SSE streaming chat endpoint with tool-call loop, memory integration, and auto-title generation.

State machine per request:
  SessionStart → (ensure daily file, load context) → Normal → [Flush if needed] → Done

Memory rules:
  - Normal conversation turns NEVER mutate memory.
  - Memory only changes via explicit tool calls (memory_append, memory_save).
  - The pre-compaction flush is the only "automatic" behaviour, and even
    that works by asking the model to call memory tools.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, g, Response, jsonify, stream_with_context
from middleware.auth import require_auth

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.openai_service import (
    stream_chat,
    build_messages,
    generate_title,
    count_tokens,
    run_flush_completion,
)
from services.memory_service import ensure_daily_file, get_session_context
from services.embedding_service import hybrid_search
from services.gateway_service import dispatch_tool_call, build_workflow_context
from tools.registry import tool_registry
from config import Config

chat_bp = Blueprint('chat', __name__)


def _save_message(conversation_id: str, role: str, **kwargs) -> dict:
    """Insert a message row and return it."""
    sb = get_supabase()
    data = {'conversation_id': conversation_id, 'role': role}
    data.update({k: v for k, v in kwargs.items() if v is not None})
    result = sb.table('messages').insert(data).execute()
    return result.data[0]


def _get_history(conversation_id: str) -> list[dict]:
    """Fetch messages for a conversation within the context window (last N hours)."""
    sb = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=Config.CHAT_HISTORY_HOURS)).isoformat()
    result = (
        sb.table('messages')
        .select('*')
        .eq('conversation_id', conversation_id)
        .gte('created_at', cutoff)
        .order('created_at', desc=False)
        .execute()
    )
    return result.data


def _is_first_exchange(conversation_id: str) -> bool:
    """Check if this is the first user message (only 1 user message exists)."""
    sb = get_supabase()
    result = (
        sb.table('messages')
        .select('id')
        .eq('conversation_id', conversation_id)
        .eq('role', 'user')
        .execute()
    )
    return len(result.data) == 1


def _update_title(conversation_id: str, user_id: str, user_msg: str, assistant_msg: str):
    """Generate and set a conversation title after the first exchange."""
    title = generate_title(user_msg, assistant_msg)
    sb = get_supabase()
    sb.table('conversations').update({'title': title}).eq('id', conversation_id).eq('user_id', user_id).execute()


def _collect_tool_sources(
    tool_name: str,
    tool_args: str | dict,
    result_str: str,
    all_sources: list[dict],
    seen_source_files: set[str],
) -> None:
    """Extract document/memory source references from tool calls and add them to all_sources."""
    try:
        args = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
    except (json.JSONDecodeError, TypeError):
        args = {}

    new_sources: list[str] = []

    if tool_name == "document_read":
        filename = args.get("filename", "")
        if filename:
            new_sources.append(f"documents/{filename}")

    elif tool_name == "memory_read":
        date_str = args.get("date")
        if date_str:
            new_sources.append(f"daily/{date_str}.md")
        else:
            from datetime import date
            new_sources.append(f"daily/{date.today().isoformat()}.md")

    elif tool_name == "memory_search":
        # Parse the result to extract source files
        try:
            result_data = json.loads(result_str) if isinstance(result_str, str) else result_str
            for r in result_data.get("results", []):
                sf = r.get("source_file", "")
                if sf:
                    new_sources.append(sf)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    elif tool_name in ("accounting_list_accounts", "accounting_search_transactions"):
        new_sources.append("accounting/integration")

    for sf in new_sources:
        if sf not in seen_source_files:
            seen_source_files.add(sf)
            all_sources.append({"source_file": sf, "score": 1.0})


def _run_silent_flush(conversation_id: str, memory_context: str) -> None:
    """
    Pre-compaction memory flush: silent turn (NO_REPLY to user).

    If the conversation is approaching the context window limit, ask the
    model to persist durable facts via memory tools.  This is the only
    "automatic" memory behaviour.  The model still calls the tools
    explicitly; we just prompt it to do so.
    """
    # Make conversation_id available to tool functions via Flask g
    g.conversation_id = conversation_id

    history = _get_history(conversation_id)
    messages = build_messages(
        history,
        memory_context=memory_context,
        history_hours=Config.CHAT_HISTORY_HOURS,
    )

    tool_calls = run_flush_completion(messages)
    if not tool_calls:
        return  # model decided nothing worth saving

    # Save the (silent) assistant message with tool calls
    _save_message(
        conversation_id,
        'assistant',
        tool_calls=tool_calls,
        model=Config.OPENAI_MODEL,
    )

    # Execute each tool call and save results -- all silent, no SSE
    for tc in tool_calls:
        tool_name = tc['function']['name']
        tool_args = tc['function']['arguments']
        tool_call_id = tc['id']

        result_str = tool_registry.execute(tool_name, tool_args)

        _save_message(
            conversation_id,
            'tool',
            content=result_str,
            tool_call_id=tool_call_id,
        )


@chat_bp.route('/chat/<conversation_id>', methods=['POST'])
@require_auth
def chat(conversation_id: str):
    """
    Accept a user message and stream back the assistant response via SSE.

    Request body: { "message": "user's message text" }

    SSE event types: thinking, content, tool_call, tool_result, title, done, error
    """
    sb = get_supabase()

    # Verify conversation belongs to user
    conv = (
        sb.table('conversations')
        .select('id, title')
        .eq('id', conversation_id)
        .eq('user_id', g.user_id)
        .single()
        .execute()
    )
    if not conv.data:
        return jsonify({'error': 'Conversation not found'}), 404

    body = request.get_json(silent=True) or {}
    user_message = body.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400

    # ── Session-start bookkeeping (idempotent) ───────────────────
    # Create today's daily file if absent (no content generation).
    # Then read today + yesterday as passive, read-only context.
    # Both calls are wrapped so Storage issues never block the chat.
    memory_context = ""
    try:
        ensure_daily_file(g.user_id)
    except Exception:
        log.exception("ensure_daily_file failed for user=%s", g.user_id)
    try:
        memory_context = get_session_context(g.user_id)
    except Exception:
        log.exception("get_session_context failed for user=%s", g.user_id)

    # ── Automatic RAG retrieval ───────────────────────────────────
    # Search the memory index using the user's message and inject
    # relevant historical context into the prompt.  Results from
    # today/yesterday daily logs are filtered out (already in
    # memory_context).  Search failures never block the chat.
    retrieved_context = ""
    rag_sources: list[dict] = []  # deduplicated list of source references
    try:
        from datetime import date, timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)
        skip_files = {
            f"daily/{today.isoformat()}.md",
            f"daily/{yesterday.isoformat()}.md",
        }

        rag_results = hybrid_search(
            g.user_id, user_message, Config.RAG_RESULT_LIMIT
        )

        # Filter: remove chunks already in session context and low-score noise
        filtered = [
            r for r in rag_results
            if r["source_file"] not in skip_files
            and r.get("score", 0) >= Config.RAG_MIN_SCORE
        ]

        if filtered:
            parts = []
            seen_sources: set[str] = set()
            for r in filtered:
                parts.append(
                    f"<source: {r['source_file']}>\n{r['chunk_text']}"
                )
                if r["source_file"] not in seen_sources:
                    seen_sources.add(r["source_file"])
                    rag_sources.append({
                        "source_file": r["source_file"],
                        "score": round(r.get("score", 0), 4),
                    })
            retrieved_context = "\n\n".join(parts)
    except Exception:
        log.exception("RAG retrieval failed for user=%s conv=%s", g.user_id, conversation_id)

    # ── Workflow context (pending approvals, active runs) ────────
    workflow_context = ""
    try:
        workflow_context = build_workflow_context(g.user_id) or ""
    except Exception:
        log.exception("build_workflow_context failed for user=%s", g.user_id)

    # Save user message
    _save_message(conversation_id, 'user', content=user_message)

    def generate():
        """SSE generator with tool-call loop and pre-compaction flush."""
        # Make conversation_id available to tool functions via Flask g
        g.conversation_id = conversation_id

        # Collect all sources referenced during this response (RAG + tools)
        all_sources: list[dict] = list(rag_sources)  # start with RAG sources
        seen_source_files: set[str] = {s["source_file"] for s in all_sources}

        # Emit initial RAG sources so the frontend can show citations early
        if rag_sources:
            yield f"event: sources\ndata: {json.dumps({'sources': rag_sources})}\n\n"

        max_tool_rounds = 10
        rounds = 0
        flush_done = False

        while rounds < max_tool_rounds:
            rounds += 1

            # Get conversation history (last N hours only)
            history = _get_history(conversation_id)

            full_retrieved = retrieved_context
            if workflow_context:
                full_retrieved = (
                    (retrieved_context + "\n\n" + workflow_context)
                    if retrieved_context
                    else workflow_context
                )

            messages = build_messages(
                history,
                memory_context=memory_context,
                retrieved_context=full_retrieved,
                history_hours=Config.CHAT_HISTORY_HOURS,
            )

            # ── Pre-compaction flush check ────────────────────────
            # Only run once per request to avoid loops.
            if not flush_done:
                token_count = count_tokens(messages)
                if token_count >= Config.MEMORY_FLUSH_TOKEN_THRESHOLD:
                    flush_done = True
                    try:
                        _run_silent_flush(conversation_id, memory_context)
                    except Exception:
                        log.exception("Silent flush failed for conv=%s", conversation_id)
                    # Re-fetch history after flush (it may have added messages)
                    history = _get_history(conversation_id)
                    messages = build_messages(
                        history,
                        memory_context=memory_context,
                        retrieved_context=full_retrieved,
                        history_hours=Config.CHAT_HISTORY_HOURS,
                    )

            # Stream from OpenAI
            final_data = None
            for event_str in stream_chat(messages):
                yield event_str

                # Parse the done event to get final data
                if event_str.startswith('event: done'):
                    data_line = event_str.split('data: ', 1)[1].split('\n')[0]
                    final_data = json.loads(data_line)

                # If error, stop
                if event_str.startswith('event: error'):
                    return

            if final_data is None:
                return

            # Save assistant message (include sources on the final response)
            save_kwargs = {
                'content': final_data.get('content') or None,
                'thinking': final_data.get('thinking') or None,
                'tool_calls': final_data.get('tool_calls'),
                'model': Config.OPENAI_MODEL,
            }
            # Attach sources to the final assistant message (the one with content, no tool calls)
            if not final_data.get('tool_calls') and all_sources:
                save_kwargs['sources'] = all_sources
            _save_message(conversation_id, 'assistant', **save_kwargs)

            # If there are tool calls, execute them and loop
            tool_calls = final_data.get('tool_calls')
            if not tool_calls:
                # No tool calls -- we're done.
                # Auto-generate title if first exchange
                try:
                    if _is_first_exchange(conversation_id):
                        _update_title(
                            conversation_id,
                            g.user_id,
                            user_message,
                            final_data.get('content', ''),
                        )
                        # Emit title event
                        sb2 = get_supabase()
                        updated = (
                            sb2.table('conversations')
                            .select('title')
                            .eq('id', conversation_id)
                            .single()
                            .execute()
                        )
                        if updated.data:
                            yield f"event: title\ndata: {json.dumps({'title': updated.data['title']})}\n\n"
                except Exception:
                    log.exception("Title generation failed for conv=%s", conversation_id)
                return

            # Execute each tool call through the gateway
            for tc in tool_calls:
                tool_name = tc['function']['name']
                tool_args = tc['function']['arguments']
                tool_call_id = tc['id']

                result_str = dispatch_tool_call(
                    tool_name, tool_args, g.user_id, conversation_id
                )

                # Save tool result message
                _save_message(
                    conversation_id,
                    'tool',
                    content=result_str,
                    tool_call_id=tool_call_id,
                )

                # Track document sources from tool calls
                _collect_tool_sources(
                    tool_name, tool_args, result_str,
                    all_sources, seen_source_files,
                )

                # Emit tool result event
                yield f"event: tool_result\ndata: {json.dumps({'tool_call_id': tool_call_id, 'name': tool_name, 'result': result_str})}\n\n"

            # Emit updated sources if tools added new ones
            if len(all_sources) > len(rag_sources):
                yield f"event: sources\ndata: {json.dumps({'sources': all_sources})}\n\n"

            # Loop will re-fetch history and call OpenAI again

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
