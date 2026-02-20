import logging
from functools import wraps
from flask import request, g, jsonify
from services.supabase_service import get_supabase

log = logging.getLogger(__name__)


def require_auth(f):
    """Decorator that verifies the Supabase token via the Supabase API and injects g.user_id.

    Accepts the token either from the ``Authorization: Bearer <token>`` header
    or from a ``?token=<token>`` query parameter (needed for ``EventSource``
    connections which don't support custom headers).
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        elif request.args.get('token'):
            token = request.args['token']
        else:
            log.warning("Auth failed — missing/malformed header on %s %s", request.method, request.path)
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        try:
            sb = get_supabase()
            user_response = sb.auth.get_user(token)
            g.user_id = user_response.user.id
        except Exception:
            log.warning("Auth failed — invalid/expired token on %s %s", request.method, request.path, exc_info=True)
            return jsonify({'error': 'Invalid or expired token'}), 401

        return f(*args, **kwargs)

    return decorated
