"""
Memories API: browse, read, edit memory files and view access logs.

All endpoints require authentication via @require_auth.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from flask import Blueprint, g, jsonify, request
from middleware.auth import require_auth

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services import memory_service, embedding_service

memories_bp = Blueprint('memories', __name__)


# ── List all memory files with access counts ─────────────────────────

@memories_bp.route('/memories', methods=['GET'])
@require_auth
def list_memories():
    """Return all memory files for the user with per-file access counts."""
    user_id = g.user_id
    sb = get_supabase()

    # Get daily log filenames from Storage
    daily_filenames = memory_service.list_daily_logs(user_id)

    # Get access counts grouped by source_file
    access_counts: dict[str, int] = {}
    try:
        result = (
            sb.table('memory_access_log')
            .select('source_file')
            .eq('user_id', user_id)
            .execute()
        )
        for row in result.data:
            sf = row.get('source_file')
            if sf:
                access_counts[sf] = access_counts.get(sf, 0) + 1
    except Exception:
        log.exception("Failed to fetch access counts for user=%s", user_id)

    # Build daily list (sorted newest first)
    daily = []
    for filename in sorted(daily_filenames, reverse=True):
        # filename is e.g. "2025-02-08.md"
        date_str = filename.replace('.md', '')
        source_file = f"daily/{filename}"
        daily.append({
            'date': date_str,
            'source_file': source_file,
            'access_count': access_counts.get(source_file, 0),
        })

    # Check if MEMORY.md exists
    long_term_content = memory_service.get_long_term_memory(user_id)
    long_term = {
        'source_file': 'MEMORY.md',
        'exists': long_term_content is not None,
        'access_count': access_counts.get('MEMORY.md', 0),
    }

    return jsonify({'daily': daily, 'long_term': long_term})


# ── Daily log CRUD ───────────────────────────────────────────────────

@memories_bp.route('/memories/daily/<date_str>', methods=['GET'])
@require_auth
def get_daily(date_str: str):
    """Return the content of a specific daily log."""
    user_id = g.user_id
    try:
        d = date_cls.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': f'Invalid date format: {date_str}. Use YYYY-MM-DD.'}), 400

    content = memory_service.get_daily_log(user_id, d)
    if content is None:
        return jsonify({'error': f'No daily log found for {date_str}.'}), 404

    return jsonify({'date': date_str, 'source_file': f'daily/{date_str}.md', 'content': content})


@memories_bp.route('/memories/daily/<date_str>', methods=['PUT'])
@require_auth
def update_daily(date_str: str):
    """Replace the content of a daily log and re-index."""
    user_id = g.user_id
    try:
        d = date_cls.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': f'Invalid date format: {date_str}. Use YYYY-MM-DD.'}), 400

    body = request.get_json(silent=True) or {}
    content = body.get('content')
    if content is None:
        return jsonify({'error': 'content is required'}), 400

    source_file = f"daily/{date_str}.md"

    # Replace the file content via the memory service
    memory_service.replace_daily_log(user_id, d, content)

    # Re-index the updated file
    try:
        embedding_service.index_memory_file(user_id, source_file, content)
    except Exception:
        log.exception("Re-indexing failed for %s user=%s", source_file, user_id)

    return jsonify({'date': date_str, 'source_file': source_file, 'content': content})


# ── Long-term memory (MEMORY.md) ────────────────────────────────────

@memories_bp.route('/memories/long-term', methods=['GET'])
@require_auth
def get_long_term():
    """Return the content of MEMORY.md."""
    user_id = g.user_id
    content = memory_service.get_long_term_memory(user_id)
    if content is None:
        return jsonify({'error': 'MEMORY.md not found.'}), 404

    return jsonify({'source_file': 'MEMORY.md', 'content': content})


@memories_bp.route('/memories/long-term', methods=['PUT'])
@require_auth
def update_long_term():
    """Replace the content of MEMORY.md and re-index."""
    user_id = g.user_id
    body = request.get_json(silent=True) or {}
    content = body.get('content')
    if content is None:
        return jsonify({'error': 'content is required'}), 400

    # Use 'replace' mode to overwrite the entire file
    memory_service.save_long_term_memory(user_id, content, mode='replace')

    # Re-index the updated file
    try:
        embedding_service.index_memory_file(user_id, 'MEMORY.md', content)
    except Exception:
        log.exception("Re-indexing MEMORY.md failed for user=%s", user_id)

    return jsonify({'source_file': 'MEMORY.md', 'content': content})


# ── Access log ───────────────────────────────────────────────────────

@memories_bp.route('/memories/access-log/<path:source_file>', methods=['GET'])
@require_auth
def get_access_log(source_file: str):
    """
    Return the access log for a specific memory file.

    Joins with conversations to include conversation titles.
    """
    user_id = g.user_id
    sb = get_supabase()

    try:
        result = (
            sb.table('memory_access_log')
            .select('id, conversation_id, tool_name, created_at')
            .eq('user_id', user_id)
            .eq('source_file', source_file)
            .order('created_at', desc=True)
            .execute()
        )
    except Exception:
        log.exception("Failed to fetch access log for %s user=%s", source_file, user_id)
        return jsonify([])

    # Collect unique conversation IDs to fetch titles
    conv_ids = list({row['conversation_id'] for row in result.data})
    conv_titles: dict[str, str] = {}
    if conv_ids:
        try:
            convs = (
                sb.table('conversations')
                .select('id, title')
                .in_('id', conv_ids)
                .execute()
            )
            conv_titles = {c['id']: c['title'] for c in convs.data}
        except Exception:
            log.exception("Failed to fetch conversation titles for access log")

    entries = [
        {
            'id': row['id'],
            'conversation_id': row['conversation_id'],
            'conversation_title': conv_titles.get(row['conversation_id'], 'Unknown'),
            'tool_name': row['tool_name'],
            'created_at': row['created_at'],
        }
        for row in result.data
    ]

    return jsonify(entries)
