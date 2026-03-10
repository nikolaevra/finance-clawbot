"""Celery application factory with Flask app context integration.

Usage:
    Worker:  celery -A celery_app.celery worker --loglevel=info
    Beat:    celery -A celery_app.celery beat --loglevel=info
    Both:    celery -A celery_app.celery worker --beat --loglevel=info
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from config import Config

celery = Celery("finance_clawbot")

celery.conf.update(
    broker_url=Config.CELERY_BROKER_URL,
    result_backend=Config.CELERY_RESULT_BACKEND,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
    include=[
        "tasks.workflow_tasks",
        "tasks.document_tasks",
        "tasks.analysis_tasks",
        "tasks.memory_tasks",
        "tasks.skill_automation_tasks",
        "tasks.gmail_watch_tasks",
        "tasks.email_sync_tasks",
    ],
)

_flask_app = None


def get_flask_app():
    """Lazy-create the Flask app so Celery tasks can use Flask context."""
    global _flask_app
    if _flask_app is None:
        from app import create_app
        _flask_app = create_app()
    return _flask_app


class FlaskTask(celery.Task):
    """Base task that runs inside a Flask application context."""

    def __call__(self, *args, **kwargs):
        with get_flask_app().app_context():
            return self.run(*args, **kwargs)


celery.Task = FlaskTask


@celery.on_after_configure.connect
def _setup_beat_schedule(sender, **kwargs):
    from tasks.scheduled import beat_schedule
    sender.conf.beat_schedule = beat_schedule
