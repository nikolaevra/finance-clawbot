from __future__ import annotations

import types

import services.openai_service as openai_service


def test_summarize_email_thread_preview_returns_normalized_text(monkeypatch):
    class _OpenAI:
        class chat:
            class completions:
                @staticmethod
                def create(*_args, **_kwargs):
                    return types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                message=types.SimpleNamespace(
                                    content="  Concise   thread   summary with spaces.  "
                                )
                            )
                        ]
                    )

    monkeypatch.setattr(openai_service, "get_openai", lambda: _OpenAI())

    summary = openai_service.summarize_email_thread_preview(
        "subject",
        [
            {
                "from_json": {"email": "person@example.com"},
                "body_text": "Please review the updated numbers and confirm by Friday.",
                "snippet": "",
            }
        ],
    )

    assert summary == "Concise thread summary with spaces."


def test_summarize_email_thread_preview_returns_none_without_usable_messages():
    summary = openai_service.summarize_email_thread_preview(
        "subject",
        [{"from_json": {"email": "a@b.com"}, "body_text": "", "snippet": ""}],
    )
    assert summary is None

