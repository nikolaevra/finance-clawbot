from __future__ import annotations

from flask import g

import services.automation_wait_service as wait_service
import services.inbound_event_adapter_service as adapter_service
import tools.automation_tools as automation_tools


def test_create_wait_and_match_pending(monkeypatch, fake_supabase, request_context):
    monkeypatch.setattr(wait_service, "get_supabase", lambda: fake_supabase)
    g.user_id = "user-1"
    g.conversation_id = "conv-1"
    g.current_tool_call_id = "tool-1"

    out = automation_tools.await_external_response(
        channel="email",
        matcher={
            "all": [
                {"field": "sender_email", "op": "equals", "value": "nikolaevra@gmail.com"},
                {"field": "subject", "op": "contains", "value": "confirmation"},
            ]
        },
        timeout_minutes=30,
    )

    assert out["status"] == "awaiting_external_response"
    wait_id = out["wait_id"]
    wait = wait_service.get_wait(wait_id)
    assert wait is not None
    assert wait["tool_call_id"] == "tool-1"

    inbound = wait_service.record_inbound_event(
        provider="gmail",
        provider_event_id="gmail:int-1:msg-1",
        user_id="user-1",
        channel="email",
        normalized_event={
            "sender_email": "nikolaevra@gmail.com",
            "subject": "Positive confirmation",
            "body_text": "yes confirmed",
        },
    )
    matched = wait_service.match_pending_wait(
        user_id="user-1",
        channel="email",
        inbound_event=inbound["normalized_event_json"],
        inbound_event_id=inbound["id"],
    )
    assert matched is not None
    assert matched["id"] == wait_id
    assert matched["status"] == "matched"


def test_matcher_supports_any_and_legacy_keys():
    event = {
        "sender": "Nikolaevra <nikolaevra@gmail.com>",
        "sender_email": "nikolaevra@gmail.com",
        "subject": "Re: approval",
        "body_text": "Got it. yes",
        "thread_ref": "thread-1",
    }
    assert wait_service.evaluate_matcher(
        {
            "from_contains": "nikolaevra@gmail.com",
            "thread_id": "thread-1",
            "body_contains_any": ["yes", "confirmed"],
        },
        event,
    )


def test_expire_pending_waits(monkeypatch, fake_supabase):
    fake_supabase.tables["automation_waits"] = [
        {
            "id": "wait-1",
            "user_id": "user-1",
            "conversation_id": "conv-1",
            "status": "pending",
            "timeout_at": "2020-01-01T00:00:00+00:00",
        }
    ]
    monkeypatch.setattr(wait_service, "get_supabase", lambda: fake_supabase)
    expired = wait_service.expire_pending_waits(now_iso="2026-01-01T00:00:00+00:00")
    assert expired == 1
    assert fake_supabase.tables["automation_waits"][0]["status"] == "expired"


def test_normalize_gmail_event():
    normalized = adapter_service.normalize_event(
        provider="gmail",
        user_id="user-1",
        integration_id="int-1",
        payload={
            "message_id": "msg-1",
            "thread_id": "thread-1",
            "from": "Nik <nikolaevra@gmail.com>",
            "subject": "Please confirm",
            "snippet": "yes",
            "label_ids": ["INBOX"],
            "is_inbox": True,
        },
    )
    assert normalized["provider_event_id"] == "gmail:int-1:msg-1"
    assert normalized["channel"] == "email"
    assert normalized["sender_email"] == "nikolaevra@gmail.com"
