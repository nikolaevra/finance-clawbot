"""Celery Beat schedule configuration.

Import this module's ``beat_schedule`` in ``celery_app.py`` or merge it
via ``celery.conf.beat_schedule.update()``.
"""
import logging

from celery.schedules import crontab

log = logging.getLogger(__name__)

beat_schedule = {
    "daily-memory-consolidation": {
        "task": "tasks.memory_tasks.consolidate_all_users",
        "schedule": crontab(minute=0, hour=0),
    },
}

log.info("beat_schedule_loaded jobs=%s", ",".join(sorted(beat_schedule.keys())))
