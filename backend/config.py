import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"{key} is required in .env")
    return value


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Flask
    FLASK_ENV = os.getenv("FLASK_ENV", "development").lower()
    ENVIRONMENT = os.getenv("ENVIRONMENT", FLASK_ENV).lower()
    IS_PRODUCTION = ENVIRONMENT in {"production", "prod"}

    # FLASK_DEBUG always wins when explicitly set.
    # Otherwise, disable debug whenever ENVIRONMENT is production-like.
    _flask_debug_raw = os.getenv("FLASK_DEBUG")
    DEBUG = (
        _as_bool(_flask_debug_raw)
        if _flask_debug_raw is not None
        else (FLASK_ENV == "development" and not IS_PRODUCTION)
    )
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = _require_env('OPENAI_MODEL')
    OPENAI_MINI_MODEL = _require_env('OPENAI_MINI_MODEL')
    OPENAI_EMBEDDING_MODEL = _require_env('OPENAI_EMBEDDING_MODEL')

    # Memory
    MEMORY_BUCKET = os.getenv('MEMORY_BUCKET', 'memory')
    MEMORY_FLUSH_TOKEN_THRESHOLD = int(os.getenv('MEMORY_FLUSH_TOKEN_THRESHOLD', '100000'))

    # Chat context — how far back to include conversation history
    CHAT_HISTORY_HOURS = int(os.getenv('CHAT_HISTORY_HOURS', '48'))

    # RAG — automatic memory retrieval per chat request
    RAG_RESULT_LIMIT = int(os.getenv('RAG_RESULT_LIMIT', '5'))
    RAG_MIN_SCORE = float(os.getenv('RAG_MIN_SCORE', '0.3'))

    # Merge.dev
    MERGE_API_KEY = os.getenv('MERGE_API_KEY', '')

    # Google OAuth (Gmail + Workspace)
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
    GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5001/api/integrations/gmail/callback')
    GOOGLE_WORKSPACE_REDIRECT_URI = os.getenv(
        'GOOGLE_WORKSPACE_REDIRECT_URI',
        'http://localhost:5001/api/integrations/google-workspace/callback',
    )
    GMAIL_WEBHOOK_SECRET = os.getenv('GMAIL_WEBHOOK_SECRET', '')
    GMAIL_WATCH_TOPIC = os.getenv('GMAIL_WATCH_TOPIC', '')
    ENABLE_GMAIL_WATCHER = _as_bool(os.getenv("ENABLE_GMAIL_WATCHER"), True)

    # Celery
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

    # CORS
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
