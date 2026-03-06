from __future__ import annotations

import services.gmail_service as gmail_service
import services.skill_service as skill_service


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
    )
    assert saved["name"] == "budgeting"

    prompt = skill_service.load_skills_for_prompt("user-1")
    assert "<skills>" in (prompt or "")
    assert 'name="budgeting"' in (prompt or "")

    toggled = skill_service.toggle_skill("user-1", "budgeting", False)
    assert toggled is not None
    assert toggled["enabled"] is False
