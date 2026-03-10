"""Thin HTTP adapter for the chat endpoint.

All orchestration (context assembly, agent loop, tool dispatch, persistence)
is handled by the Gateway control plane.  This route only validates the
HTTP request and delegates to ``gateway.handle_message``.
"""
from __future__ import annotations

import logging

from flask import Blueprint, request, g, Response, jsonify, stream_with_context
from middleware.auth import require_auth
from services.supabase_service import get_supabase
from services.gateway_service import gateway

chat_bp = Blueprint('chat', __name__)
log = logging.getLogger(__name__)


@chat_bp.route('/chat/<conversation_id>', methods=['POST'])
@require_auth
def chat(conversation_id: str):
    """Accept a user message and stream back the assistant response via SSE.

    Request body: { "message": "user's message text" }
    SSE event types: thinking, content, tool_call, tool_result, sources, title, done, error
    """
    sb = get_supabase()

    conv = (
        sb.table('conversations')
        .select('id, title')
        .eq('id', conversation_id)
        .eq('user_id', g.user_id)
        .single()
        .execute()
    )
    if not conv.data:
        log.warning("chat_conversation_not_found user=%s conversation=%s", g.user_id, conversation_id)
        return jsonify({'error': 'Conversation not found'}), 404

    body = request.get_json(silent=True) or {}
    user_message = body.get('message', '').strip()
    forced_skill = (body.get('forced_skill') or '').strip() or None
    if not user_message:
        log.warning("chat_empty_message user=%s conversation=%s", g.user_id, conversation_id)
        return jsonify({'error': 'Message is required'}), 400

    log.info(
        "chat_stream_start user=%s conversation=%s chars=%d",
        g.user_id,
        conversation_id,
        len(user_message),
    )

    return Response(
        stream_with_context(
            gateway.handle_message(
                g.user_id,
                conversation_id,
                user_message,
                forced_skill=forced_skill,
            )
        ),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@chat_bp.route('/chat/<conversation_id>/approve-tools', methods=['POST'])
@require_auth
def approve_tools(conversation_id: str):
    """Approve or reject pending tool calls and continue the agent loop.

    Request body: { "tool_call_ids": [...], "approved": true/false }
    Returns an SSE stream so the LLM can respond after tool execution.
    """
    sb = get_supabase()

    conv = (
        sb.table('conversations')
        .select('id')
        .eq('id', conversation_id)
        .eq('user_id', g.user_id)
        .single()
        .execute()
    )
    if not conv.data:
        log.warning("approve_tools_conversation_not_found user=%s conversation=%s", g.user_id, conversation_id)
        return jsonify({'error': 'Conversation not found'}), 404

    body = request.get_json(silent=True) or {}
    tool_call_ids = body.get('tool_call_ids', [])
    approved = body.get('approved', True)

    if not tool_call_ids:
        log.warning("approve_tools_missing_ids user=%s conversation=%s", g.user_id, conversation_id)
        return jsonify({'error': 'tool_call_ids is required'}), 400

    log.info(
        "approve_tools user=%s conversation=%s count=%d approved=%s",
        g.user_id,
        conversation_id,
        len(tool_call_ids),
        bool(approved),
    )

    return Response(
        stream_with_context(
            gateway.resume_after_approval(
                g.user_id, conversation_id, tool_call_ids, approved,
            )
        ),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
