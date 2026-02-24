import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


class Config:
    # Flask
    DEBUG = os.getenv('FLASK_ENV', 'development') == 'development'

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'o4-mini')
    OPENAI_EMBEDDING_MODEL = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')

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

    # Google OAuth (Gmail)
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
    GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5001/api/integrations/gmail/callback')

    # Celery
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

    # CORS
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
