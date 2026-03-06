api:         cd backend && gunicorn run:app --bind 0.0.0.0:${PORT:-5001} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-120}
worker-beat: cd backend && celery -A celery_app.celery worker --beat --loglevel=${CELERY_LOG_LEVEL:-info} --concurrency=${CELERY_CONCURRENCY:-2}
