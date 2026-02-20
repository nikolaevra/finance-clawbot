from flask import Blueprint, request, jsonify, g
from middleware.auth import require_auth
from services.supabase_service import get_supabase

conversations_bp = Blueprint('conversations', __name__)


@conversations_bp.route('/conversations', methods=['GET'])
@require_auth
def list_conversations():
    """List all conversations for the authenticated user, newest first."""
    sb = get_supabase()
    result = (
        sb.table('conversations')
        .select('id, title, created_at, updated_at')
        .eq('user_id', g.user_id)
        .order('updated_at', desc=True)
        .execute()
    )
    return jsonify(result.data)


@conversations_bp.route('/conversations', methods=['POST'])
@require_auth
def create_conversation():
    """Create a new conversation."""
    sb = get_supabase()
    body = request.get_json(silent=True) or {}
    title = body.get('title', 'New Chat')

    result = (
        sb.table('conversations')
        .insert({'user_id': g.user_id, 'title': title})
        .execute()
    )
    return jsonify(result.data[0]), 201


@conversations_bp.route('/conversations/current', methods=['GET'])
@require_auth
def get_or_create_current():
    """Return the user's single conversation (creating it if needed), with all messages."""
    sb = get_supabase()

    # Find existing conversation (oldest first — there should be at most one used)
    result = (
        sb.table('conversations')
        .select('*')
        .eq('user_id', g.user_id)
        .order('created_at', desc=False)
        .limit(1)
        .execute()
    )

    if result.data:
        conv = result.data[0]
    else:
        conv = (
            sb.table('conversations')
            .insert({'user_id': g.user_id, 'title': 'Finance Assistant'})
            .execute()
        ).data[0]

    # Fetch messages ordered by creation time
    msgs = (
        sb.table('messages')
        .select('*')
        .eq('conversation_id', conv['id'])
        .order('created_at', desc=False)
        .execute()
    )

    return jsonify({**conv, 'messages': msgs.data})


@conversations_bp.route('/conversations/<conversation_id>', methods=['GET'])
@require_auth
def get_conversation(conversation_id: str):
    """Get a single conversation with all its messages."""
    sb = get_supabase()

    # Fetch conversation (verify ownership)
    conv = (
        sb.table('conversations')
        .select('*')
        .eq('id', conversation_id)
        .eq('user_id', g.user_id)
        .single()
        .execute()
    )
    if not conv.data:
        return jsonify({'error': 'Conversation not found'}), 404

    # Fetch messages ordered by creation time
    msgs = (
        sb.table('messages')
        .select('*')
        .eq('conversation_id', conversation_id)
        .order('created_at', desc=False)
        .execute()
    )

    return jsonify({**conv.data, 'messages': msgs.data})


@conversations_bp.route('/conversations/<conversation_id>', methods=['PATCH'])
@require_auth
def update_conversation(conversation_id: str):
    """Update conversation title."""
    sb = get_supabase()
    body = request.get_json(silent=True) or {}

    update_data = {}
    if 'title' in body:
        update_data['title'] = body['title']

    if not update_data:
        return jsonify({'error': 'No fields to update'}), 400

    result = (
        sb.table('conversations')
        .update(update_data)
        .eq('id', conversation_id)
        .eq('user_id', g.user_id)
        .execute()
    )

    if not result.data:
        return jsonify({'error': 'Conversation not found'}), 404

    return jsonify(result.data[0])


@conversations_bp.route('/conversations/<conversation_id>', methods=['DELETE'])
@require_auth
def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages (cascade)."""
    sb = get_supabase()

    result = (
        sb.table('conversations')
        .delete()
        .eq('id', conversation_id)
        .eq('user_id', g.user_id)
        .execute()
    )

    if not result.data:
        return jsonify({'error': 'Conversation not found'}), 404

    return jsonify({'success': True})
