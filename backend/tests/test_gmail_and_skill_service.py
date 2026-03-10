from __future__ import annotations

import pytest

import services.gmail_service as gmail_service
import services.skill_service as skill_service
import routes.skills as skills_routes


class _FakeCredentials:
    def to_json(self) -> str:
        return '{"access_token":"token"}'


class _FakeFlow:
    last_created: "_FakeFlow | None" = None

    def __init__(self) -> None:
        self.redirect_uri = ""
        self.code_verifier = None
        self.authorization_kwargs = {}
        self.fetch_kwargs = {}
        self.credentials = _FakeCredentials()

    @classmethod
    def from_client_config(cls, _client_config, scopes):
        flow = cls()
        flow.scopes = scopes
        cls.last_created = flow
        return flow

    def authorization_url(self, **kwargs):
        self.authorization_kwargs = kwargs
        return "https://accounts.google.com/mock-auth", kwargs.get("state")

    def fetch_token(self, **kwargs):
        self.fetch_kwargs = kwargs


def test_extract_attachment_metadata_walks_nested_parts():
    payload = {
        "parts": [
            {
                "filename": "invoice.pdf",
                "mimeType": "application/pdf",
                "body": {"attachmentId": "att-1", "size": 123},
            },
            {
                "parts": [
                    {
                        "filename": "data.csv",
                        "mimeType": "text/csv",
                        "body": {"attachmentId": "att-2", "size": 50},
                    }
                ]
            },
        ]
    }
    out = gmail_service._extract_attachment_metadata(payload)
    assert {row["attachment_id"] for row in out} == {"att-1", "att-2"}


def test_build_and_parse_oauth_state_roundtrip():
    state = gmail_service.build_oauth_state("user-123", "pkce-verifier")
    user_id, code_verifier = gmail_service.parse_oauth_state(state)
    assert user_id == "user-123"
    assert code_verifier == "pkce-verifier"


def test_parse_oauth_state_accepts_legacy_plain_state():
    user_id, code_verifier = gmail_service.parse_oauth_state("legacy-user-id")
    assert user_id == "legacy-user-id"
    assert code_verifier is None


def test_parse_oauth_state_rejects_tampered_signature():
    state = gmail_service.build_oauth_state("user-123", "pkce-verifier")
    bad_state = f"{state[:-1]}x"
    with pytest.raises(ValueError):
        gmail_service.parse_oauth_state(bad_state)


def test_get_auth_url_embeds_signed_state_and_pkce(monkeypatch):
    monkeypatch.setattr(gmail_service, "Flow", _FakeFlow)
    url = gmail_service.get_auth_url("user-789")

    assert url == "https://accounts.google.com/mock-auth"
    flow = _FakeFlow.last_created
    assert flow is not None
    auth_kwargs = flow.authorization_kwargs
    assert auth_kwargs["code_challenge_method"] == "S256"
    state = auth_kwargs.get("state", "")
    parsed_user_id, parsed_code_verifier = gmail_service.parse_oauth_state(state)
    assert parsed_user_id == "user-789"
    assert parsed_code_verifier
    assert flow.code_verifier == parsed_code_verifier


def test_exchange_code_passes_code_verifier_to_fetch_token(monkeypatch):
    monkeypatch.setattr(gmail_service, "Flow", _FakeFlow)
    creds = gmail_service.exchange_code("oauth-code", code_verifier="pkce-verifier")
    assert creds == '{"access_token":"token"}'

    flow = _FakeFlow.last_created
    assert flow is not None
    assert flow.fetch_kwargs["code"] == "oauth-code"
    assert flow.fetch_kwargs["code_verifier"] == "pkce-verifier"


def test_skill_frontmatter_and_prompt_loading(monkeypatch, fake_supabase):
    monkeypatch.setattr(skill_service, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(skill_service, "STORAGE_BUCKET", "skills-test")
    skill_service._bucket_ready = False

    meta = skill_service._parse_frontmatter(
        "---\ndescription: test skill\nenabled: true\n---\nbody"
    )
    assert meta["description"] == "test skill"

    saved = skill_service.save_skill(
        "user-1",
        "budgeting",
        "---\ndescription: Budget helper\nenabled: true\n---\n# Skill",
        {
            "schedule_enabled": True,
            "schedule_type": "daily",
            "schedule_time": "08:00",
            "schedule_timezone": "UTC",
            "trigger_enabled": True,
            "trigger_provider": "gmail",
            "trigger_event": "new_email",
            "trigger_filters": {"inbox_only": True},
        },
    )
    assert saved["name"] == "budgeting"
    assert saved["schedule_enabled"] is True
    assert saved["trigger_enabled"] is True

    prompt = skill_service.load_skills_for_prompt("user-1")
    assert "<skills>" in (prompt or "")
    assert 'name="budgeting"' in (prompt or "")

    toggled = skill_service.toggle_skill("user-1", "budgeting", False)
    assert toggled is not None
    assert toggled["enabled"] is False


def test_automation_validation_accepts_weekly_and_gmail_trigger():
    payload = {
        "enabled": True,
        "schedule_enabled": True,
        "schedule_type": "weekly",
        "schedule_days": [1, 3, 5],
        "schedule_time": "09:15",
        "schedule_timezone": "America/New_York",
        "trigger_enabled": True,
        "trigger_provider": "gmail",
        "trigger_event": "new_email",
        "trigger_filters": {
            "inbox_only": True,
            "from_contains": "billing@",
            "subject_contains": "invoice",
        },
    }
    out, err = skills_routes._validate_automation(payload)
    assert err is None
    assert out["schedule_enabled"] is True
    assert out["trigger_enabled"] is True


def test_automation_validation_rejects_bad_time():
    out, err = skills_routes._validate_automation(
        {
            "schedule_enabled": True,
            "schedule_type": "daily",
            "schedule_time": "25:99",
            "schedule_timezone": "UTC",
        }
    )
    assert out == {}
    assert "schedule_time" in (err or "")
