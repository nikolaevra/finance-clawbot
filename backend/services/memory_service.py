"""
Memory service: pure Storage I/O for daily logs, MEMORY.md, and bootstrap files.

No indexing logic lives here. This module is responsible for:
- Session-start bookkeeping (ensure today's daily file exists)
- Reading / appending daily logs from Supabase Storage
- Reading / writing long-term MEMORY.md
- Bootstrap prompt files (SOUL, IDENTITY, USER, AGENTS, TOOLS, BOOTSTRAP)
- Building read-only session context (today + yesterday)
"""
from __future__ import annotations

from datetime import date, timedelta
from services.supabase_service import get_supabase
from config import Config

_bucket_ready = False


def _ensure_bucket() -> None:
    """Lazily create the memory Storage bucket if it doesn't exist."""
    global _bucket_ready
    if _bucket_ready:
        return
    sb = get_supabase()
    try:
        sb.storage.get_bucket(Config.MEMORY_BUCKET)
    except Exception:
        sb.storage.create_bucket(
            Config.MEMORY_BUCKET,
            options={"public": False},
        )
    _bucket_ready = True


def _storage():
    """Return a storage client scoped to the memory bucket."""
    _ensure_bucket()
    return get_supabase().storage.from_(Config.MEMORY_BUCKET)


def _daily_path(user_id: str, d: date) -> str:
    """Build the Storage path for a daily log file."""
    return f"{user_id}/daily/{d.isoformat()}.md"


def _memory_path(user_id: str) -> str:
    """Build the Storage path for long-term MEMORY.md."""
    return f"{user_id}/MEMORY.md"


# ── Session-start bookkeeping ────────────────────────────────────────

def ensure_daily_file(user_id: str) -> str:
    """
    Create today's YYYY-MM-DD.md in Storage if it doesn't already exist.

    This is pure bookkeeping: an empty file with a date header.
    No summarisation, no content generation.

    Returns the Storage path of today's file.
    """
    today = date.today()
    path = _daily_path(user_id, today)

    # Check if the file already exists by attempting to download it
    try:
        _storage().download(path)
        return path  # already exists
    except Exception:
        pass  # file doesn't exist yet

    # Create with a date header
    header = f"# {today.isoformat()}\n\n"
    _storage().upload(
        path,
        header.encode("utf-8"),
        {"content-type": "text/markdown"},
    )
    return path


# ── Daily log operations ─────────────────────────────────────────────

def get_daily_log(user_id: str, d: date | None = None) -> str | None:
    """Download a daily log from Storage.  Returns None if file doesn't exist."""
    d = d or date.today()
    path = _daily_path(user_id, d)
    try:
        data = _storage().download(path)
        return data.decode("utf-8") if isinstance(data, bytes) else data
    except Exception:
        return None


def append_daily_log(user_id: str, content: str) -> str:
    """
    Append content to today's daily log (download → append → re-upload).

    Returns the full updated content of the file.
    """
    today = date.today()
    path = _daily_path(user_id, today)

    # Get existing content (or create file if absent)
    existing = get_daily_log(user_id, today)
    if existing is None:
        ensure_daily_file(user_id)
        existing = f"# {today.isoformat()}\n\n"

    updated = existing.rstrip("\n") + "\n\n" + content.strip() + "\n"

    # Re-upload (Supabase Storage update = overwrite)
    _storage().update(
        path,
        updated.encode("utf-8"),
        {"content-type": "text/markdown"},
    )
    return updated


def replace_daily_log(user_id: str, d: date, content: str) -> str:
    """
    Replace the entire content of a daily log file.

    Creates the file if it doesn't exist.  Returns the content written.
    """
    path = _daily_path(user_id, d)
    existing = get_daily_log(user_id, d)

    try:
        if existing is not None:
            _storage().update(
                path,
                content.encode("utf-8"),
                {"content-type": "text/markdown"},
            )
        else:
            _storage().upload(
                path,
                content.encode("utf-8"),
                {"content-type": "text/markdown"},
            )
    except Exception:
        # If update fails, try upload
        _storage().upload(
            path,
            content.encode("utf-8"),
            {"content-type": "text/markdown"},
        )
    return content


def list_daily_logs(user_id: str) -> list[str]:
    """List all daily log filenames for a user."""
    prefix = f"{user_id}/daily/"
    try:
        files = _storage().list(prefix)
        return [f["name"] for f in files if f.get("name", "").endswith(".md")]
    except Exception:
        return []


# ── Long-term memory (MEMORY.md) ────────────────────────────────────

def get_long_term_memory(user_id: str) -> str | None:
    """Download MEMORY.md from Storage.  Returns None if it doesn't exist."""
    path = _memory_path(user_id)
    try:
        data = _storage().download(path)
        return data.decode("utf-8") if isinstance(data, bytes) else data
    except Exception:
        return None


def save_long_term_memory(user_id: str, content: str, mode: str = "append") -> str:
    """
    Write to MEMORY.md.

    mode="append"  → add content to the end of the existing file.
    mode="replace" → overwrite the entire file.

    Returns the full content after the write.
    """
    path = _memory_path(user_id)
    existing = get_long_term_memory(user_id)

    if mode == "replace" or existing is None:
        final = content.strip() + "\n"
    else:
        final = existing.rstrip("\n") + "\n\n" + content.strip() + "\n"

    try:
        if existing is not None:
            _storage().update(
                path,
                final.encode("utf-8"),
                {"content-type": "text/markdown"},
            )
        else:
            _storage().upload(
                path,
                final.encode("utf-8"),
                {"content-type": "text/markdown"},
            )
    except Exception:
        # If update fails (e.g. file was deleted), try upload
        _storage().upload(
            path,
            final.encode("utf-8"),
            {"content-type": "text/markdown"},
        )

    return final


# ── Bootstrap files ───────────────────────────────────────────────────
#
# Injection order mirrors OpenClaw:
#   SOUL.md     → personality, boundaries, vibe
#   IDENTITY.md → name, avatar, emoji, creature
#   USER.md     → human's profile and preferences
#   AGENTS.md   → operating instructions, memory workflow, safety
#   TOOLS.md    → environment-specific notes (device names, SSH, etc.)
#   BOOTSTRAP.md→ first-run onboarding script (deleted after setup)

_BOOTSTRAP_FILES = (
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "AGENTS.md",
    "TOOLS.md",
    "BOOTSTRAP.md",
)
_BOOTSTRAP_FILES_SET = frozenset(_BOOTSTRAP_FILES)
_BOOTSTRAP_MAX_PER_FILE = 20_000
_BOOTSTRAP_MAX_TOTAL = 80_000


def _bootstrap_path(user_id: str, filename: str) -> str:
    return f"{user_id}/{filename}"


def get_bootstrap_file(user_id: str, filename: str) -> str | None:
    """Download a single bootstrap file. Returns None if it doesn't exist."""
    if filename not in _BOOTSTRAP_FILES_SET:
        return None
    path = _bootstrap_path(user_id, filename)
    try:
        data = _storage().download(path)
        return data.decode("utf-8") if isinstance(data, bytes) else data
    except Exception:
        return None


def save_bootstrap_file(user_id: str, filename: str, content: str) -> str:
    """Write a bootstrap file (create or overwrite). Returns content written."""
    if filename not in _BOOTSTRAP_FILES_SET:
        raise ValueError(f"Invalid bootstrap file: {filename}")
    path = _bootstrap_path(user_id, filename)
    encoded = content.encode("utf-8")
    try:
        _storage().update(path, encoded, {"content-type": "text/markdown"})
    except Exception:
        _storage().upload(path, encoded, {"content-type": "text/markdown"})
    return content


def delete_bootstrap_file(user_id: str, filename: str) -> bool:
    """Delete a bootstrap file. Returns True if removed, False otherwise."""
    if filename not in _BOOTSTRAP_FILES_SET:
        return False
    path = _bootstrap_path(user_id, filename)
    try:
        _storage().remove([path])
        return True
    except Exception:
        return False


def has_bootstrap_file(user_id: str) -> bool:
    """Return True if BOOTSTRAP.md exists for this user (first-run check)."""
    return get_bootstrap_file(user_id, "BOOTSTRAP.md") is not None


def load_bootstrap_files(user_id: str) -> str:
    """Load and concatenate all bootstrap files for prompt injection.

    Follows OpenClaw's injection order: SOUL → IDENTITY → USER → AGENTS → TOOLS.
    BOOTSTRAP.md is included only when it exists (first-run); after the
    agent completes onboarding it should delete the file.

    Each file is capped at 20k chars, total at 80k chars.
    Returns an empty string if no files exist.
    """
    parts: list[str] = []
    total = 0
    for filename in _BOOTSTRAP_FILES:
        content = get_bootstrap_file(user_id, filename)
        if not content:
            continue
        content = content[:_BOOTSTRAP_MAX_PER_FILE]
        if total + len(content) > _BOOTSTRAP_MAX_TOTAL:
            content = content[:_BOOTSTRAP_MAX_TOTAL - total]
        if content:
            label = filename.replace(".md", "")
            parts.append(f"[{label}]\n{content}")
            total += len(content)
    return "\n\n---\n\n".join(parts)


# ── Auto-seed bootstrap files for new users ──────────────────────────

def ensure_bootstrap_files(user_id: str) -> None:
    """Seed default bootstrap templates for any files that don't exist yet.

    Called once per session start (idempotent).  Only uploads a template
    when the file is completely absent — never overwrites user content.
    """
    from services.bootstrap_templates import TEMPLATES

    for filename, template in TEMPLATES.items():
        if get_bootstrap_file(user_id, filename) is not None:
            continue
        path = _bootstrap_path(user_id, filename)
        try:
            _storage().upload(
                path,
                template.encode("utf-8"),
                {"content-type": "text/markdown"},
            )
        except Exception:
            pass  # best-effort; don't block the session


# ── Session context (read-only) ─────────────────────────────────────

def get_session_context(user_id: str) -> str:
    """
    Read today + yesterday daily logs and concatenate them into a context block.

    This is read-only.  No writes, no summarisation, no reinterpretation.
    Returns an empty string if neither file exists.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    parts: list[str] = []

    yesterday_log = get_daily_log(user_id, yesterday)
    if yesterday_log:
        parts.append(f"[Yesterday — {yesterday.isoformat()}]\n{yesterday_log}")

    today_log = get_daily_log(user_id, today)
    if today_log:
        parts.append(f"[Today — {today.isoformat()}]\n{today_log}")

    return "\n\n---\n\n".join(parts)
