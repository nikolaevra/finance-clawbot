redis:    redis-server --port 6379
backend:  cd backend && source venv/bin/activate && python run.py
worker:   cd backend && source venv/bin/activate && celery -A celery_app.celery worker --beat --loglevel=info
frontend: cd frontend && npm run dev
