from __future__ import annotations

import services.gmail_service as gmail_service
import services.skill_service as skill_service
import routes.skills as skills_routes


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
