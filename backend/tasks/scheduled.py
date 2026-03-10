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
    # Gmail watch expires periodically (~7 days), so refresh twice daily.
    "refresh-gmail-watches": {
        "task": "tasks.gmail_watch_tasks.refresh_all_gmail_watches",
        "schedule": crontab(minute=0, hour="*/12"),
    },
    "sync-gmail-history-deltas": {
        "task": "tasks.email_sync_tasks.sync_all_gmail_history_deltas",
        "schedule": crontab(minute="*/5"),
    },
    "scan-scheduled-automations": {
        "task": "tasks.skill_automation_tasks.scan_scheduled_automations",
        "schedule": crontab(minute="*"),
    },
}

log.info("beat_schedule_loaded jobs=%s", ",".join(sorted(beat_schedule.keys())))
