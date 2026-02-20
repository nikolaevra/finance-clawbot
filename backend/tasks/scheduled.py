"""Celery Beat schedule configuration.

Import this module's ``beat_schedule`` in ``celery_app.py`` or merge it
via ``celery.conf.beat_schedule.update()``.
"""
from celery.schedules import crontab

beat_schedule = {
    "sync-all-integrations": {
        "task": "tasks.sync_tasks.sync_all_active_integrations",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "daily-memory-consolidation": {
        "task": "tasks.memory_tasks.consolidate_all_users",
        "schedule": crontab(minute=0, hour=0),
    },
    "daily-anomaly-detection": {
        "task": "tasks.analysis_tasks.run_anomaly_detection_all",
        "schedule": crontab(minute=30, hour=8),
    },
}
