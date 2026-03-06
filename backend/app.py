import logging
import time
import uuid

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from config import Config
from logging_config import setup_logging

log = logging.getLogger(__name__)


def create_app() -> Flask:
    setup_logging()

    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app, resources={r"/api/*": {"origins": Config.FRONTEND_URL}},
         supports_credentials=True)

    # ── Request / response logging ────────────────────────────────
    @app.before_request
    def _log_request_start():
        g.req_start = time.monotonic()
        # Reuse incoming request IDs from proxies/CDNs, otherwise generate one.
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        if request.path != "/api/health":
            log.info(
                "request_start id=%s method=%s path=%s ip=%s ua=%s auth=%s",
                g.request_id,
                request.method,
                request.path,
                request.headers.get("X-Forwarded-For", request.remote_addr or "-"),
                request.user_agent.string[:120] if request.user_agent else "-",
                "yes" if request.headers.get("Authorization") else "no",
            )

    @app.after_request
    def _log_request_end(response):
        request_id = getattr(g, "request_id", "-")
        response.headers["X-Request-ID"] = request_id
        if request.path == "/api/health":
            return response
        elapsed = (time.monotonic() - getattr(g, "req_start", 0)) * 1000
        log.info(
            "request_end id=%s method=%s path=%s status=%s duration_ms=%.0f user=%s",
            request_id,
            request.method,
            request.path,
            response.status_code,
            elapsed,
            getattr(g, "user_id", "-"),
        )
        return response

    # ── Global error handlers ─────────────────────────────────────
    @app.errorhandler(404)
    def _not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def _server_error(e):
        log.exception(
            "Unhandled 500 error id=%s method=%s path=%s",
            getattr(g, "request_id", "-"),
            request.method,
            request.path,
        )
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(Exception)
    def _handle_exception(e):
        log.exception(
            "Unhandled exception id=%s method=%s path=%s",
            getattr(g, "request_id", "-"),
            request.method,
            request.path,
        )
        return jsonify({"error": "Internal server error"}), 500

    # ── Register blueprints ───────────────────────────────────────
    from routes.conversations import conversations_bp
    from routes.chat import chat_bp
    from routes.memories import memories_bp
    from routes.documents import documents_bp
    from routes.integrations import integrations_bp
    from routes.workflows import workflows_bp
    from routes.activity import activity_bp
    from routes.skills import skills_bp

    app.register_blueprint(conversations_bp, url_prefix='/api')
    app.register_blueprint(chat_bp, url_prefix='/api')
    app.register_blueprint(memories_bp, url_prefix='/api')
    app.register_blueprint(documents_bp, url_prefix='/api')
    app.register_blueprint(integrations_bp, url_prefix='/api')
    app.register_blueprint(workflows_bp, url_prefix='/api')
    app.register_blueprint(activity_bp, url_prefix='/api')
    app.register_blueprint(skills_bp, url_prefix='/api')

    @app.route('/api/health')
    def health():
        return {'status': 'ok'}

    log.info("Flask app created — blueprints registered")
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(port=5000, debug=Config.DEBUG)
