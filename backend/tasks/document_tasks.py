"""Document processing tasks — async text extraction and indexing.

Wraps the existing ``document_service.process_document`` as a Celery task
so uploads return immediately.
"""
from __future__ import annotations

import logging

from celery_app import celery
from services.document_service import process_document as _process_document

log = logging.getLogger(__name__)


@celery.task(name="tasks.document_tasks.process_document")
def process_document(user_id: str, document_id: str, storage_path: str, file_type: str) -> dict:
    """Extract text, summarise, and index a newly uploaded document."""
    log.info("process_document started doc=%s type=%s user=%s", document_id, file_type, user_id)
    _process_document(user_id, document_id, storage_path, file_type)
    log.info("process_document completed doc=%s", document_id)
    return {"status": "ok", "document_id": document_id}
