"""Thin HTTP adapter for the chat endpoint.

All orchestration (context assembly, agent loop, tool dispatch, persistence)
is handled by the Gateway control plane.  This route only validates the
HTTP request and delegates to ``gateway.handle_message``.
"""
from __future__ import annotations

from flask import Blueprint, request, g, Response, jsonify, stream_with_context
from middleware.auth import require_auth
from services.supabase_service import get_supabase
from services.gateway_service import gateway

chat_bp = Blueprint('chat', __name__)


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
        return jsonify({'error': 'Conversation not found'}), 404

    body = request.get_json(silent=True) or {}
    user_message = body.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400

    return Response(
        stream_with_context(
            gateway.handle_message(g.user_id, conversation_id, user_message)
        ),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
