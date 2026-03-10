from __future__ import annotations

from flask import g

import tools.gmail_tools as gmail_tools


def _enable_fake_is_null_filter(monkeypatch):
    from tests.fakes import FakeTable

    def _is(self, key, value):
        if value == "null":
            self._filters.append(("eq", key, None))
            return self
        self._filters.append(("eq", key, value))
        return self

    monkeypatch.setattr(FakeTable, "is_", _is, raising=False)


def test_gmail_list_messages_uses_local_cache_only(
    monkeypatch, request_context, fake_supabase
):
    _enable_fake_is_null_filter(monkeypatch)
    g.user_id = "user-1"
    fake_supabase.tables["integrations"] = [
        {
            "id": "int-1",
            "user_id": "user-1",
            "provider": "gmail",
            "status": "active",
            "account_token": '{"access_token":"x"}',
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    fake_supabase.tables["emails"] = [
        {
            "gmail_message_id": "msg-1",
            "gmail_thread_id": "thr-1",
            "subject": "Invoice 123",
            "snippet": "Invoice attached",
            "from_json": {"name": "Alice", "email": "alice@example.com"},
            "to_json": [{"name": "Bob", "email": "bob@example.com"}],
            "internal_date_ts": 1700000000000,
            "label_ids_json": ["INBOX", "UNREAD"],
            "is_read": False,
            "is_sent": False,
            "is_draft": False,
            "integration_id": "int-1",
            "user_id": "user-1",
            "deleted_at": None,
        }
    ]
    monkeypatch.setattr(gmail_tools, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(
        gmail_tools.gmail_service,
        "list_messages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Remote Gmail API should not be called")
        ),
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        gmail_tools, "_enqueue_delta_sync", lambda integration_id: enqueued.append(integration_id) or True
    )

    out = gmail_tools.gmail_list_messages(query="in:inbox", refresh_local=True)

    assert out["tool_used"] == "gmail_list_messages"
    assert out["source"] == "Local cache"
    assert out["sync_enqueued"] is True
    assert out["total_results"] == 1
    assert out["messages"][0]["id"] == "msg-1"
    assert enqueued == ["int-1"]


def test_gmail_get_message_uses_local_cache_only(
    monkeypatch, request_context, fake_supabase
):
    _enable_fake_is_null_filter(monkeypatch)
    g.user_id = "user-1"
    fake_supabase.tables["integrations"] = [
        {
            "id": "int-1",
            "user_id": "user-1",
            "provider": "gmail",
            "status": "active",
            "account_token": '{"access_token":"x"}',
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    fake_supabase.tables["emails"] = [
        {
            "gmail_message_id": "msg-9",
            "gmail_thread_id": "thr-9",
            "subject": "Draft",
            "snippet": "Body",
            "body_text": "Local cached body",
            "from_json": {"name": "Alice", "email": "alice@example.com"},
            "to_json": [{"name": "Bob", "email": "bob@example.com"}],
            "cc_json": [],
            "internal_date_ts": 1700000000000,
            "label_ids_json": ["INBOX"],
            "integration_id": "int-1",
            "user_id": "user-1",
            "deleted_at": None,
        }
    ]
    monkeypatch.setattr(gmail_tools, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(
        gmail_tools.gmail_service,
        "get_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Remote Gmail API should not be called")
        ),
    )

    out = gmail_tools.gmail_get_message("msg-9")

    assert out["tool_used"] == "gmail_get_message"
    assert out["source"] == "Local cache"
    assert out["message"]["id"] == "msg-9"
    assert out["message"]["body_text"] == "Local cached body"


def test_gmail_send_message_enqueues_sync_and_hydration(monkeypatch, request_context):
    g.user_id = "user-1"
    monkeypatch.setattr(
        gmail_tools,
        "_get_gmail_integration",
        lambda: {"id": "int-7", "account_token": '{"access_token":"x"}'},
    )
    monkeypatch.setattr(
        gmail_tools.gmail_service,
        "send_message",
        lambda *_args, **_kwargs: {"id": "msg-sent", "threadId": "thr-sent"},
    )
    sync_calls: list[str] = []
    hydration_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gmail_tools, "_enqueue_delta_sync", lambda integration_id: sync_calls.append(integration_id) or True
    )
    monkeypatch.setattr(
        gmail_tools,
        "_enqueue_message_hydration",
        lambda integration_id, message_id: hydration_calls.append((integration_id, message_id)) or True,
    )

    out = gmail_tools.gmail_send_message("to@example.com", "Subj", "Body", cc="")

    assert out["source"] == "In-app Gmail integration"
    assert out["sync_enqueued"] is True
    assert out["hydration_enqueued"] is True
    assert sync_calls == ["int-7"]
    assert hydration_calls == [("int-7", "msg-sent")]


def test_gmail_modify_labels_updates_local_cache(monkeypatch, request_context, fake_supabase):
    _enable_fake_is_null_filter(monkeypatch)
    g.user_id = "user-1"
    fake_supabase.tables["emails"] = [
        {
            "gmail_message_id": "msg-42",
            "label_ids_json": ["INBOX", "UNREAD"],
            "is_read": False,
            "is_sent": False,
            "is_draft": False,
            "integration_id": "int-1",
            "user_id": "user-1",
            "deleted_at": None,
        }
    ]
    monkeypatch.setattr(gmail_tools, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(
        gmail_tools,
        "_get_gmail_integration",
        lambda: {"id": "int-1", "account_token": '{"access_token":"x"}'},
    )
    monkeypatch.setattr(
        gmail_tools.gmail_service,
        "modify_labels",
        lambda *_args, **_kwargs: {"id": "msg-42", "labelIds": ["INBOX"]},
    )
    sync_calls: list[str] = []
    monkeypatch.setattr(
        gmail_tools, "_enqueue_delta_sync", lambda integration_id: sync_calls.append(integration_id) or True
    )

    out = gmail_tools.gmail_modify_labels(
        "msg-42",
        add_label_ids=["STARRED"],
        remove_label_ids=["UNREAD"],
    )

    assert out["source"] == "In-app Gmail integration"
    assert sorted(out["updated_labels"]) == ["INBOX", "STARRED"]
    assert out["sync_enqueued"] is True
    assert sync_calls == ["int-1"]

    updated_row = fake_supabase.tables["emails"][0]
    assert sorted(updated_row["label_ids_json"]) == ["INBOX", "STARRED"]
    assert updated_row["is_read"] is True
