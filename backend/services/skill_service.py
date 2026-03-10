"""Skill service — manages user-editable skills stored in Supabase Storage.

Skills are markdown files (SKILL.md) with YAML frontmatter for metadata.
The DB ``skills`` table is a lightweight metadata index for fast listing;
the actual content lives in Supabase Storage under
``skills/{user_id}/{skill_name}/SKILL.md``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any

import frontmatter

from services.supabase_service import get_supabase

log = logging.getLogger(__name__)

STORAGE_BUCKET = "skills"
MAX_SKILLS_IN_PROMPT = 50
MAX_SKILLS_PROMPT_CHARS = 15_000
DEFAULT_ONBOARDING_SKILL_NAME = "guided-onboarding-account-setup"
FINANCE_INBOX_TRIAGE_SKILL_NAME = "finance-inbox-triage"
FLOAT_SPEND_OVERVIEW_SKILL_NAME = "float-spend-overview-cfo"
SKILL_CREATOR_PLANNER_NAME = "skill-creator-planner"
AUTOMATION_FRONTMATTER_KEYS = {
    "enabled",
    "schedule_enabled",
    "schedule_type",
    "schedule_days",
    "schedule_time",
    "schedule_timezone",
    "trigger_enabled",
    "trigger_provider",
    "trigger_event",
    "trigger_filters",
}

DEFAULT_ONBOARDING_SKILL_CONTENT = dedent(
    """\
    ---
    name: guided-onboarding-account-setup
    description: Runs a guided onboarding and account-creation flow. Use when the user asks what you can do, wants onboarding, account setup, email inbox setup, Gmail automations, or accounting integration setup.
    ---

    # Guided Onboarding + Account Setup

    ## Goal
    Run a complete, step-by-step onboarding that:
    1. Explains assistant capabilities in plain language
    2. Sets up required memory files (especially USER.md and long-term memory)
    3. Verifies or guides connection of Gmail and accounting integrations
    4. Ends with a concrete "ready to use" checklist

    ## How To Run This Skill
    Follow the steps in order. Keep each step short, clear, and actionable.
    Do not skip checks even if the user sounds ready.

    ### Step 1 - Capability Overview
    - Explain what you can do:
      - Inbox management (read/summarize/draft/reply/forward with confirmation when sending)
      - Finance analysis from connected accounting systems
      - Tracking and recalling context via memory files
      - Running repeatable skills and automations
    - End this step by asking: "Want me to guide you through full setup now?"

    ### Step 2 - Identity + User Profile Memory Setup
    Your objective is to set up profile context even on day 1.

    - Ask for missing essentials:
      - preferred name
      - timezone
      - company/business name
      - role
      - primary finance priorities (for example: cash flow, expenses, invoicing)
    - Persist what you learn:
      - Use memory_save to store durable profile facts in MEMORY.md
      - Use memory_append to add today's onboarding notes to daily memory
    - If USER.md is incomplete or stale:
      - Tell the user exactly what fields should be filled in USER.md
      - Offer to generate a clean USER.md draft they can paste into the Memories editor

    ### Step 3 - Email Setup Check (Inbox + Drafting + Automations)
    - Confirm whether Gmail integration is connected.
    - If not connected, provide this setup sequence:
      1. Open Integrations page
      2. Connect Gmail
      3. Return here and say "Gmail connected"
    - After connected, explain what unlocks:
      - Manage inbox from chat
      - Draft replies quickly
      - Trigger automations when new emails arrive (for example: invoice triage, follow-up draft prep)
    - Ask whether they want an email-trigger automation configured next.

    ### Step 4 - Accounting Setup Check
    - Confirm whether an accounting integration is connected (QuickBooks / NetSuite / Float as available).
    - If not connected, provide this setup sequence:
      1. Open Integrations page
      2. Connect accounting system
      3. Return here and say "Accounting connected"
    - After connected, explain what unlocks:
      - account and transaction lookup
      - spend analysis and anomaly checks
      - bill and reporting assistance

    ### Step 5 - Completion Checklist + Next Action
    End with a checklist showing status:
    - [ ] USER profile captured
    - [ ] Memory baseline saved
    - [ ] Gmail connected
    - [ ] Accounting connected
    - [ ] First automation selected

    Then propose exactly one high-value next action based on missing items.

    ## Output Style
    - Keep guidance practical and concise.
    - Prefer numbered steps and checklists over long paragraphs.
    - Ask one setup question at a time during onboarding.
    """
)

FINANCE_INBOX_TRIAGE_SKILL_CONTENT = dedent(
    """\
    ---
    name: finance-inbox-triage
    description: Triages finance-related inbox messages into needs action, important review, updates, and non-urgent. Use when user asks to prioritize finance emails.
    ---

    # Finance Inbox Triage

    ## Goal
    Review the user's finance-related inbox items and classify each message into exactly one bucket:
    1. needs action
    2. important review
    3. updates
    4. non-urgent

    ## Inputs and tools
    - Use `gmail_list_messages` to fetch relevant recent messages.
    - Use `gmail_get_message` for any message that needs deeper inspection.
    - Prefer local cache reads first. If data looks stale, request a refresh using `gmail_refresh_local_emails` and continue once available.

    ## Triage rules
    Classify with these default rules unless the user gives overrides:

    - **needs action**
      - Requires a direct response, approval, payment, filing, or deadline-driven task.
      - Examples: overdue invoice notices, approval requests, missing-doc requests, tax/payment reminders.
      - High urgency or clear "you must do X" language.

    - **important review**
      - No immediate action required, but financially meaningful and should be reviewed soon.
      - Examples: large bills, unusual charges, monthly statements, contract/pricing changes.

    - **updates**
      - Informational finance updates with low risk and no immediate action.
      - Examples: receipt confirmations, successful payment notifications, status updates.

    - **non-urgent**
      - Low-value, promotional, repetitive, or not materially relevant to finance decisions.
      - Examples: newsletters, marketing offers, generic announcements.

    ## Output format
    - Return a concise triage summary grouped by bucket.
    - For each email include: subject, sender, date, and one-line reason for classification.
    - Keep ordering by priority:
      1) needs action
      2) important review
      3) updates
      4) non-urgent
    - If `needs action` contains items, add a short "Suggested next actions" list.
    - If no relevant messages are found, say so and suggest broadening the query window.

    ## Safety and confidence
    - Do not fabricate missing details.
    - If confidence is low for an item, flag it as "needs manual check" and explain why.
    - Prefer conservative escalation: when uncertain between `updates` and `important review`, choose `important review`.
    """
)

FLOAT_SPEND_OVERVIEW_SKILL_CONTENT = dedent(
    """\
    ---
    name: float-spend-overview-cfo
    description: Builds a CFO-level Float spend overview across bills, account/card transactions, and reimbursements with week-over-week and month-over-month movement analysis.
    ---

    # Float Spend Overview (CFO)

    ## Goal
    Produce an executive-ready spend summary that explains:
    - where money is going,
    - how spend changed week over week,
    - how spend changed month over month,
    - the biggest movers over the last week and the last 3 months.

    Include spend across:
    - bill payments (`float_bill_payments`)
    - card transactions (`float_card_transactions`)
    - account transactions (`float_account_transactions`)
    - reimbursements (`float_reimbursements`)

    ## Required output sections
    1. Executive summary (5-8 bullets)
    2. Top 25 vendors table (week-over-week view)
    3. Top 25 users table (week-over-week view)
    4. Biggest movers week-over-week (up and down)
    5. Last 3 months trend and biggest movers month-over-month
    6. Risks / watchouts and recommended actions

    ## Data collection process
    1. Define analysis windows:
       - current week to date
       - prior comparable week
       - current month to date
       - prior month comparable period
       - trailing 3 full months
    2. Pull data using Float tools for each window.
    3. If tool responses are paginated (especially card transactions), request additional pages until enough coverage is collected.
    4. Normalize into common fields:
       - date
       - amount (positive spend in absolute terms)
       - currency
       - source_type (card/account/bill/reimbursement)
       - vendor (merchant_name, vendor_external_id, or best available label)
       - user (spender, submitter_email, or closest owner)
    5. Exclude obvious non-spend inflows/credits when preparing spend totals.

    ## Metric definitions
    - WoW change = current_week_spend - prior_week_spend
    - WoW change % = WoW change / max(prior_week_spend, small_baseline)
    - MoM change = current_month_spend - prior_month_spend
    - MoM change % = MoM change / max(prior_month_spend, small_baseline)
    - Use `small_baseline` to avoid divide-by-zero explosions and clearly note when prior period was near zero.

    ## Table requirements
    Output markdown tables with readable currency formatting.

    ### Top 25 vendors (WoW)
    Columns:
    - Rank
    - Vendor
    - Current Week Spend
    - Prior Week Spend
    - WoW Delta
    - WoW Delta %
    - Share of Current Week Spend
    - Primary Spend Type (card/bill/account/reimbursement)

    ### Top 25 users (WoW)
    Columns:
    - Rank
    - User
    - Current Week Spend
    - Prior Week Spend
    - WoW Delta
    - WoW Delta %
    - Share of Current Week Spend
    - Dominant Spend Category/Type

    ## Biggest movers
    Provide two concise lists for each period:
    - Biggest increases
    - Biggest decreases
    For each mover include:
    - name (vendor or user)
    - absolute change
    - percent change
    - likely driver (if inferable from available metadata)

    ## CFO narrative style
    - Keep language business-focused, not tool-focused.
    - Highlight concentration risk (top vendors/users share).
    - Flag anomalies, one-off spikes, and sustained trends separately.
    - End with 3-5 clear actions a CFO can take this week.

    ## Data quality guardrails
    - If coverage is incomplete (pagination limits, missing vendor/user fields, mixed currencies), state limitations explicitly before conclusions.
    - Do not fabricate vendor or user names.
    - When confidence is low, label findings as directional.
    """
)

SKILL_CREATOR_PLANNER_CONTENT = dedent(
    """\
    ---
    name: skill-creator-planner
    description: Runs a structured interview to design a new skill, then creates it in-app using the skill_create tool after user confirmation.
    ---

    # Skill Creator Planner

    ## Goal
    Help the user create a high-quality new skill by:
    1. asking a short sequence of planning questions,
    2. drafting the skill content,
    3. confirming with the user,
    4. creating the skill using `skill_create`.

    ## Process
    Ask questions one step at a time. Keep questions concise and practical.

    ### Step 1: Clarify purpose
    Collect:
    - primary outcome of the skill
    - who/what it should help with
    - when it should be triggered or used
    - what "good output" looks like

    ### Step 2: Gather operational details
    Collect:
    - required tools and data sources
    - constraints, edge cases, and exclusions
    - desired output format (tables, bullets, checklist, etc.)
    - confidence/safety requirements

    ### Step 3: Define metadata
    Propose:
    - skill slug name (lowercase kebab/underscore style)
    - one-sentence description
    - enabled/disabled default
    - optional schedule/trigger settings

    ### Step 4: Draft and confirm
    - Produce a complete SKILL.md draft with frontmatter and instructions.
    - Ask for explicit confirmation: "Create this skill now?"
    - Do not call `skill_create` without confirmation.

    ### Step 5: Create the skill
    After confirmation:
    - Call `skill_create` with the final name/content and automation settings.
    - Return creation status and a short "how to use this skill" note.

    ## Output style
    - Be collaborative and concise.
    - Ask one question at a time when requirements are incomplete.
    - When enough detail exists, switch from questions to a concrete draft quickly.
    """
)

_bucket_ready = False


def _ensure_bucket() -> None:
    """Lazily create the skills Storage bucket if it doesn't exist."""
    global _bucket_ready
    if _bucket_ready:
        return
    sb = get_supabase()
    try:
        sb.storage.get_bucket(STORAGE_BUCKET)
    except Exception:
        sb.storage.create_bucket(
            STORAGE_BUCKET,
            options={"public": False},
        )
    _bucket_ready = True


def _storage():
    """Return a storage client scoped to the skills bucket."""
    _ensure_bucket()
    return get_supabase().storage.from_(STORAGE_BUCKET)


def _storage_path(user_id: str, skill_name: str) -> str:
    return f"{user_id}/{skill_name}/SKILL.md"


def _parse_frontmatter(raw: str) -> dict[str, Any]:
    """Parse YAML frontmatter from raw markdown. Returns metadata dict."""
    try:
        post = frontmatter.loads(raw)
        return dict(post.metadata)
    except Exception:
        return {}


def _strip_automation_frontmatter(raw: str) -> str:
    """Remove automation settings from SKILL.md frontmatter.

    Automation settings are persisted in the DB, not markdown metadata.
    """
    try:
        post = frontmatter.loads(raw)
    except Exception:
        return raw

    changed = False
    for key in AUTOMATION_FRONTMATTER_KEYS:
        if key in post.metadata:
            del post.metadata[key]
            changed = True

    return frontmatter.dumps(post) if changed else raw


# ── CRUD ──────────────────────────────────────────────────────────────


def list_skills(user_id: str) -> list[dict]:
    """Return skill metadata rows from the DB for fast listing."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select(
            "id, name, description, enabled, "
            "schedule_enabled, schedule_type, schedule_days, schedule_time, schedule_timezone, "
            "trigger_enabled, trigger_provider, trigger_event, trigger_filters, "
            "created_at, updated_at"
        )
        .eq("user_id", user_id)
        .order("name")
        .execute()
    )
    return result.data or []


def get_skill(user_id: str, skill_name: str) -> str | None:
    """Read the raw SKILL.md content from Storage. Returns None if missing."""
    path = _storage_path(user_id, skill_name)
    try:
        data = _storage().download(path)
        return data.decode("utf-8") if isinstance(data, bytes) else data
    except Exception:
        log.debug("Skill not found in storage: %s", path)
        return None


def get_skill_record(user_id: str, skill_name: str) -> dict | None:
    """Return DB metadata row for a single skill."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select(
            "id, name, description, enabled, "
            "schedule_enabled, schedule_type, schedule_days, schedule_time, schedule_timezone, "
            "trigger_enabled, trigger_provider, trigger_event, trigger_filters, "
            "created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("name", skill_name)
        .limit(1)
        .execute()
    )
    if not result or not result.data:
        return None
    if isinstance(result.data, list):
        return result.data[0] if result.data else None
    return result.data


def save_skill(
    user_id: str,
    skill_name: str,
    content: str,
    automation: dict[str, Any] | None = None,
) -> dict:
    """Create or update a skill. Stores automation in DB, content in Storage."""
    meta = _parse_frontmatter(content)
    description = meta.get("description", "")
    existing = get_skill_record(user_id, skill_name) or {}
    automation = automation or {}
    enabled = bool(automation.get("enabled", existing.get("enabled", True)))
    schedule_enabled = bool(automation.get("schedule_enabled", existing.get("schedule_enabled", False)))
    schedule_type = automation.get("schedule_type", existing.get("schedule_type"))
    schedule_days = automation.get("schedule_days", existing.get("schedule_days"))
    schedule_time = automation.get("schedule_time", existing.get("schedule_time"))
    schedule_timezone = automation.get("schedule_timezone", existing.get("schedule_timezone"))
    trigger_enabled = bool(automation.get("trigger_enabled", existing.get("trigger_enabled", False)))
    trigger_provider = automation.get("trigger_provider", existing.get("trigger_provider"))
    trigger_event = automation.get("trigger_event", existing.get("trigger_event"))
    trigger_filters = automation.get("trigger_filters", existing.get("trigger_filters"))

    sb = get_supabase()
    path = _storage_path(user_id, skill_name)
    store = _storage()

    content = _strip_automation_frontmatter(content)

    content_bytes = content.encode("utf-8")
    try:
        store.update(
            path, content_bytes, {"content-type": "text/markdown"}
        )
    except Exception:
        store.upload(
            path, content_bytes, {"content-type": "text/markdown"}
        )

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id": user_id,
        "name": skill_name,
        "description": description,
        "enabled": bool(enabled),
        "schedule_enabled": schedule_enabled,
        "schedule_type": schedule_type,
        "schedule_days": schedule_days,
        "schedule_time": schedule_time,
        "schedule_timezone": schedule_timezone,
        "trigger_enabled": trigger_enabled,
        "trigger_provider": trigger_provider,
        "trigger_event": trigger_event,
        "trigger_filters": trigger_filters,
        "updated_at": now,
    }
    result = (
        sb.table("skills")
        .upsert(row, on_conflict="user_id,name")
        .execute()
    )
    return result.data[0] if result.data else row


def delete_skill(user_id: str, skill_name: str) -> bool:
    """Delete a skill from both Storage and the metadata table."""
    sb = get_supabase()
    path = _storage_path(user_id, skill_name)

    try:
        _storage().remove([path])
    except Exception:
        log.warning("Failed to remove skill file from storage: %s", path)

    sb.table("skills").delete().eq("user_id", user_id).eq("name", skill_name).execute()
    return True


def toggle_skill(user_id: str, skill_name: str, enabled: bool) -> dict | None:
    """Toggle a skill's enabled state in DB metadata."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .update({"enabled": enabled, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("user_id", user_id)
        .eq("name", skill_name)
        .execute()
    )
    if not result.data:
        return None

    return result.data[0]


def rename_skill(user_id: str, old_name: str, new_name: str) -> dict | None:
    """Rename a skill in both storage and DB metadata."""
    if old_name == new_name:
        return get_skill_record(user_id, old_name)

    existing_new = get_skill_record(user_id, new_name)
    if existing_new is not None:
        raise ValueError(f"Skill '{new_name}' already exists.")

    existing_old = get_skill_record(user_id, old_name)
    if existing_old is None:
        return None

    old_path = _storage_path(user_id, old_name)
    new_path = _storage_path(user_id, new_name)
    store = _storage()

    raw = get_skill(user_id, old_name)
    if raw is not None:
        try:
            post = frontmatter.loads(raw)
            post.metadata["name"] = new_name
            raw = frontmatter.dumps(post)
        except Exception:
            # Keep rename non-blocking if markdown cannot be parsed.
            pass
        content_bytes = raw.encode("utf-8")
        try:
            store.update(new_path, content_bytes, {"content-type": "text/markdown"})
        except Exception:
            store.upload(new_path, content_bytes, {"content-type": "text/markdown"})
        try:
            store.remove([old_path])
        except Exception:
            log.warning("Failed to remove old skill file after rename: %s", old_path)

    sb = get_supabase()
    result = (
        sb.table("skills")
        .update({"name": new_name, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("user_id", user_id)
        .eq("name", old_name)
        .execute()
    )
    return result.data[0] if result and result.data else None


def ensure_default_onboarding_skill(user_id: str) -> None:
    """Create the default guided onboarding skill when it is missing."""
    if get_skill(user_id, DEFAULT_ONBOARDING_SKILL_NAME) is not None:
        return
    save_skill(
        user_id=user_id,
        skill_name=DEFAULT_ONBOARDING_SKILL_NAME,
        content=DEFAULT_ONBOARDING_SKILL_CONTENT,
        automation={"enabled": True},
    )


def ensure_default_finance_triage_skill(user_id: str) -> None:
    """Create the default finance inbox triage skill when it is missing."""
    if get_skill(user_id, FINANCE_INBOX_TRIAGE_SKILL_NAME) is not None:
        return
    save_skill(
        user_id=user_id,
        skill_name=FINANCE_INBOX_TRIAGE_SKILL_NAME,
        content=FINANCE_INBOX_TRIAGE_SKILL_CONTENT,
        automation={"enabled": True},
    )


def ensure_default_float_spend_overview_skill(user_id: str) -> None:
    """Create the default Float spend overview skill when it is missing."""
    if get_skill(user_id, FLOAT_SPEND_OVERVIEW_SKILL_NAME) is not None:
        return
    save_skill(
        user_id=user_id,
        skill_name=FLOAT_SPEND_OVERVIEW_SKILL_NAME,
        content=FLOAT_SPEND_OVERVIEW_SKILL_CONTENT,
        automation={"enabled": True},
    )


def ensure_default_skill_creator_planner_skill(user_id: str) -> None:
    """Create the default skill creator planner skill when it is missing."""
    if get_skill(user_id, SKILL_CREATOR_PLANNER_NAME) is not None:
        return
    save_skill(
        user_id=user_id,
        skill_name=SKILL_CREATOR_PLANNER_NAME,
        content=SKILL_CREATOR_PLANNER_CONTENT,
        automation={"enabled": True},
    )


# ── Prompt injection ──────────────────────────────────────────────────


def load_skills_for_prompt(user_id: str) -> str | None:
    """Build the compact skills list for system prompt injection.

    Returns an XML-formatted block listing enabled skills with their
    name and description, or None if no skills are available.
    """
    skills = list_skills(user_id)
    enabled = [s for s in skills if s.get("enabled", True)]

    if not enabled:
        return None

    entries: list[str] = []
    total_chars = 0

    for s in enabled[:MAX_SKILLS_IN_PROMPT]:
        name = s["name"]
        desc = s.get("description") or ""
        entry = f'  <skill name="{name}">{desc}</skill>'
        if total_chars + len(entry) > MAX_SKILLS_PROMPT_CHARS:
            break
        entries.append(entry)
        total_chars += len(entry)

    if not entries:
        return None

    return "<skills>\n" + "\n".join(entries) + "\n</skills>"
