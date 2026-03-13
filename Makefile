.PHONY: dev dev-local stop install

LOCAL_RUNTIME_ENV=ENABLE_GMAIL_WATCHER=false

dev:
	@trap 'kill 0; redis-cli shutdown 2>/dev/null' EXIT; \
	redis-server --port 6379 --daemonize yes && \
	cd backend && source venv/bin/activate && \
		celery -A celery_app.celery worker --beat --loglevel=info & \
	cd backend && source venv/bin/activate && \
		python run.py & \
	cd frontend && npm run dev

dev-local:
	@trap 'kill 0; redis-cli shutdown 2>/dev/null' EXIT; \
	redis-server --port 6379 --daemonize yes && \
	cd backend && source venv/bin/activate && \
		$(LOCAL_RUNTIME_ENV) celery -A celery_app.celery worker --beat --loglevel=info & \
	cd backend && source venv/bin/activate && \
		$(LOCAL_RUNTIME_ENV) python run.py & \
	cd frontend && npm run dev

stop:
	@redis-cli shutdown 2>/dev/null || true
	@pkill -f "celery -A celery_app" 2>/dev/null || true
	@pkill -f "python run.py" 2>/dev/null || true

install:
	cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install
