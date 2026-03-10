"""Gateway service — central control plane for all message processing.

Every inbound message flows through ``Gateway.handle_message``, which owns
the full lifecycle: session context, RAG retrieval, agent loop (LLM +
tool calls), persistence, and event publishing.  HTTP routes and future
channel adapters are thin wrappers that delegate here.

Memory rules:
  - Normal conversation turns NEVER mutate memory.
  - Memory only changes via explicit tool calls (memory_append, memory_save).
  - The pre-compaction flush is the only "automatic" behaviour, and even
    that works by asking the model to call memory tools.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

from flask import g

from config import Config
from services.event_bus import publish_event
from services.supabase_service import get_supabase
from services.openai_service import (
    stream_chat,
    build_messages,
    generate_title,
    count_tokens,
    run_flush_completion,
)
from services.memory_service import (
    ensure_daily_file,
    get_session_context,
    load_bootstrap_files,
    ensure_bootstrap_files,
    has_bootstrap_file,
    delete_bootstrap_file,
)
from services.embedding_service import hybrid_search
from services.workflow_engine import (
    get_pending_approvals,
    get_active_workflows,
)
from services.skill_service import load_skills_for_prompt
from services.skill_service import ensure_default_onboarding_skill
from tools.registry import tool_registry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Human-readable event descriptions (unchanged)
# ---------------------------------------------------------------------------

_WORKFLOW_LABELS = {
    "memory_consolidation": "Memory Consolidation",
}


def _parse_args(tool_args: str | dict) -> dict:
    if isinstance(tool_args, dict):
        return tool_args
    try:
        return json.loads(tool_args) if tool_args else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _workflow_label(name: str) -> str:
    return _WORKFLOW_LABELS.get(name, name.replace("_", " ").title())


def _describe_tool(tool_name: str, args: dict) -> tuple[str, "Callable[[str | None], str]"]:
    """Return (dispatch_message, complete_message_fn) for a tool call."""
    if tool_name == "workflow_run":
        wf = args.get("workflow_name", "unknown")
        label = _workflow_label(wf)
        return (
            f"Running {label} workflow",
            lambda _r: f"Dispatched {label} to a background worker",
        )

    if tool_name == "workflow_status":
        rid = args.get("run_id", "")[:8]
        def _status_complete(r: str | None) -> str:
            try:
                d = json.loads(r) if r else {}
                wf = _workflow_label(d.get("workflow", ""))
                return f"{wf} is {d.get('status', 'unknown')}"
            except Exception:
                return f"Checked workflow status ({rid}…)"
        return (f"Checking workflow status ({rid}…)", _status_complete)

    if tool_name == "workflow_approve":
        approve = args.get("approve", True)
        action = "Approving" if approve else "Rejecting"
        return (
            f"{action} workflow run",
            lambda _r: f"Workflow {'approved and resumed' if approve else 'rejected'}",
        )

    if tool_name == "workflow_list":
        return (
            "Listing available workflows",
            lambda _r: "Retrieved workflow catalog",
        )

    _TOOL_LABELS: dict[str, tuple[str, str]] = {
        "memory_append": ("Saving to daily memory log", "Saved to memory"),
        "memory_read": ("Reading memory file", "Memory file retrieved"),
        "memory_search": ("Searching memories", "Memory search complete"),
        "memory_save": ("Writing to long-term memory", "Long-term memory updated"),
        "document_list": ("Listing uploaded documents", "Document list retrieved"),
        "document_read": ("Reading document content", "Document content retrieved"),
        "accounting_list_accounts": ("Fetching chart of accounts", "Accounts retrieved"),
        "accounting_search_transactions": ("Searching transactions", "Transaction search complete"),
        "skill_list": ("Listing available skills", "Skills list retrieved"),
        "skill_read": ("Reading skill instructions", "Skill loaded"),
        "gmail_list_messages": ("Listing Gmail messages", "Gmail messages retrieved"),
        "gmail_get_message": ("Reading Gmail message", "Gmail message retrieved"),
        "gmail_send_message": ("Sending email via Gmail", "Email sent"),
        "gmail_create_draft": ("Drafting email in Gmail", "Gmail draft created"),
        "gmail_reply_message": ("Sending reply via Gmail", "Gmail reply sent"),
        "gmail_forward_message": ("Forwarding email via Gmail", "Email forwarded"),
        "gmail_modify_labels": ("Updating Gmail labels", "Gmail labels updated"),
        "accounting_create_bill": ("Creating bill in accounting system", "Bill created"),
    }
    if tool_name in _TOOL_LABELS:
        dispatch, complete = _TOOL_LABELS[tool_name]
        return (dispatch, lambda _r, c=complete: c)

    return (
        f"Executing {tool_name.replace('_', ' ')}",
        lambda r: f"{tool_name.replace('_', ' ').capitalize()} completed",
    )


# ---------------------------------------------------------------------------
# Gateway — central control plane
# ---------------------------------------------------------------------------

class Gateway:
    """Central control plane that owns the full message lifecycle."""

    # ── Public entry point ─────────────────────────────────────────

    def handle_message(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        forced_skill: str | None = None,
    ) -> Iterator[str]:
        """Single entry point for ALL inbound messages.  Yields SSE events.

        The caller (HTTP route, future Slack/Telegram adapter, etc.) is
        responsible only for authentication and protocol framing.
        """
        publish_event(user_id, {
            "type": "message_received",
            "actor": "gateway",
            "message": "Processing message",
        })

        g.conversation_id = conversation_id

        # 1. Session context (today + yesterday daily logs)
        memory_context = self._load_session_context(user_id)

        # 2. RAG retrieval
        retrieved_context, rag_sources = self._retrieve_context(
            user_id, user_message,
        )

        # 3. Workflow context (pending approvals, active runs)
        workflow_context = ""
        try:
            workflow_context = self.build_workflow_context(user_id) or ""
        except Exception:
            log.exception("build_workflow_context failed for user=%s", user_id)

        # 4. Skills context (user-defined skills for prompt injection)
        skills_context = None
        try:
            skills_context = load_skills_for_prompt(user_id)
        except Exception:
            log.exception("load_skills_for_prompt failed for user=%s", user_id)

        # 5. Bootstrap files (SOUL, IDENTITY, USER, AGENTS, TOOLS, BOOTSTRAP)
        bootstrap_context = ""
        is_first_run = False
        try:
            is_first_run = has_bootstrap_file(user_id)
            bootstrap_context = load_bootstrap_files(user_id)
        except Exception:
            log.exception("load_bootstrap_files failed for user=%s", user_id)

        publish_event(user_id, {
            "type": "context_loaded",
            "actor": "gateway",
            "message": "Context assembled",
        })

        # 6. Persist the inbound user message
        self._save_message(conversation_id, "user", content=user_message)

        # 7. Run the agent loop (stream LLM, execute tools, re-prompt)
        yield from self._run_agent_loop(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            forced_skill=forced_skill,
            memory_context=memory_context,
            retrieved_context=retrieved_context,
            workflow_context=workflow_context,
            skills_context=skills_context,
            bootstrap_context=bootstrap_context,
            rag_sources=rag_sources,
        )

        # 8. After the first successful onboarding exchange, remove BOOTSTRAP.md
        #    so subsequent sessions skip the onboarding script.
        if is_first_run:
            try:
                delete_bootstrap_file(user_id, "BOOTSTRAP.md")
                log.info("Removed BOOTSTRAP.md after first-run for user=%s", user_id)
            except Exception:
                log.exception("Failed to remove BOOTSTRAP.md for user=%s", user_id)

        publish_event(user_id, {
            "type": "message_complete",
            "actor": "gateway",
            "message": "Response complete",
        })

    # ── Agent loop ─────────────────────────────────────────────────

    def _run_agent_loop(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message: str,
        forced_skill: str | None,
        memory_context: str,
        retrieved_context: str,
        workflow_context: str,
        skills_context: str | None,
        bootstrap_context: str = "",
        rag_sources: list[dict],
    ) -> Iterator[str]:
        """SSE generator with tool-call loop and pre-compaction flush."""
        all_sources: list[dict] = list(rag_sources)
        seen_source_files: set[str] = {s["source_file"] for s in all_sources}

        if rag_sources:
            yield f"event: sources\ndata: {json.dumps({'sources': rag_sources})}\n\n"

        max_tool_rounds = 10
        rounds = 0
        flush_done = False

        while rounds < max_tool_rounds:
            rounds += 1

            history = self._get_history(conversation_id)

            full_retrieved = retrieved_context
            if workflow_context:
                full_retrieved = (
                    (retrieved_context + "\n\n" + workflow_context)
                    if retrieved_context
                    else workflow_context
                )

            messages = build_messages(
                history,
                memory_context=memory_context,
                retrieved_context=full_retrieved,
                history_hours=Config.CHAT_HISTORY_HOURS,
                skills_context=skills_context,
                bootstrap_context=bootstrap_context or None,
            )

            if forced_skill and not self._is_skill_already_loaded(history, forced_skill):
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "For this turn, you must call skill_read first with "
                            f'skill_name="{forced_skill}" and then follow that skill.'
                        ),
                    }
                )

            # Pre-compaction flush (once per request)
            if not flush_done:
                token_count = count_tokens(messages)
                if token_count >= Config.MEMORY_FLUSH_TOKEN_THRESHOLD:
                    flush_done = True
                    try:
                        self._run_silent_flush(conversation_id, memory_context)
                    except Exception:
                        log.exception("Silent flush failed for conv=%s", conversation_id)
                    history = self._get_history(conversation_id)
                    messages = build_messages(
                        history,
                        memory_context=memory_context,
                        retrieved_context=full_retrieved,
                        history_hours=Config.CHAT_HISTORY_HOURS,
                        skills_context=skills_context,
                        bootstrap_context=bootstrap_context or None,
                    )
                    if forced_skill and not self._is_skill_already_loaded(history, forced_skill):
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "For this turn, you must call skill_read first with "
                                    f'skill_name="{forced_skill}" and then follow that skill.'
                                ),
                            }
                        )

            publish_event(user_id, {
                "type": "agent_streaming",
                "actor": "gateway",
                "message": f"Streaming response (round {rounds})",
            })

            # Stream from OpenAI
            final_data = None
            for event_str in stream_chat(messages):
                yield event_str

                if event_str.startswith("event: done"):
                    data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                    final_data = json.loads(data_line)

                if event_str.startswith("event: error"):
                    return

            if final_data is None:
                return

            # Persist assistant message
            save_kwargs = {
                "content": final_data.get("content") or None,
                "thinking": final_data.get("thinking") or None,
                "tool_calls": final_data.get("tool_calls"),
                "model": Config.OPENAI_MODEL,
            }
            if not final_data.get("tool_calls") and all_sources:
                save_kwargs["sources"] = all_sources
            self._save_message(conversation_id, "assistant", **save_kwargs)

            # If no tool calls, we're done — handle title generation
            tool_calls = final_data.get("tool_calls")
            if not tool_calls:
                try:
                    if self._is_first_exchange(conversation_id):
                        self._update_title(
                            conversation_id,
                            user_id,
                            user_message,
                            final_data.get("content", ""),
                        )
                        sb = get_supabase()
                        updated = (
                            sb.table("conversations")
                            .select("title")
                            .eq("id", conversation_id)
                            .single()
                            .execute()
                        )
                        if updated.data:
                            yield f"event: title\ndata: {json.dumps({'title': updated.data['title']})}\n\n"
                except Exception:
                    log.exception("Title generation failed for conv=%s", conversation_id)
                return

            # Partition tool calls into safe and needs-approval
            safe_calls = []
            approval_calls = []
            for tc in tool_calls:
                if tool_registry.needs_approval(tc["function"]["name"]):
                    approval_calls.append(tc)
                else:
                    safe_calls.append(tc)

            # Execute safe tool calls immediately
            for tc in safe_calls:
                tool_name = tc["function"]["name"]
                tool_args = tc["function"]["arguments"]
                tool_call_id = tc["id"]

                result_str = self.dispatch_tool_call(
                    tool_name, tool_args, user_id, conversation_id,
                )

                self._save_message(
                    conversation_id,
                    "tool",
                    content=result_str,
                    tool_call_id=tool_call_id,
                )

                self._collect_tool_sources(
                    tool_name, tool_args, result_str,
                    all_sources, seen_source_files,
                )

                yield f"event: tool_result\ndata: {json.dumps({'tool_call_id': tool_call_id, 'name': tool_name, 'result': result_str})}\n\n"

            # If any tools need approval, pause the loop
            if approval_calls:
                pending = []
                for tc in approval_calls:
                    name = tc["function"]["name"]
                    tool_obj = tool_registry.get_tool(name)
                    args = _parse_args(tc["function"]["arguments"])
                    pending.append({
                        "id": tc["id"],
                        "name": name,
                        "label": tool_obj.label if tool_obj else name,
                        "args": args,
                    })

                yield f"event: tool_approval_needed\ndata: {json.dumps({'conversation_id': conversation_id, 'tool_calls': pending})}\n\n"
                return

            if len(all_sources) > len(rag_sources):
                yield f"event: sources\ndata: {json.dumps({'sources': all_sources})}\n\n"

    # ── Tool approval resume ────────────────────────────────────────

    def resume_after_approval(
        self,
        user_id: str,
        conversation_id: str,
        tool_call_ids: list[str],
        approved: bool,
    ) -> Iterator[str]:
        """Resume the agent loop after the user approves or rejects tool calls.

        Looks up the pending tool calls from the last assistant message,
        executes (or rejects) them, then continues the agent loop so the
        LLM can produce a final response.
        """
        g.conversation_id = conversation_id

        # Find the most recent assistant message with unresolved tool calls
        history = self._get_history(conversation_id)
        pending_tc: list[dict] = []
        for msg in reversed(history):
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                resolved_ids = {
                    m["tool_call_id"]
                    for m in history
                    if m["role"] == "tool" and m.get("tool_call_id")
                }
                for tc in msg["tool_calls"]:
                    if tc["id"] in tool_call_ids and tc["id"] not in resolved_ids:
                        pending_tc.append(tc)
                break

        if not pending_tc:
            yield f"event: error\ndata: {json.dumps({'error': 'No pending tool calls found'})}\n\n"
            return

        for tc in pending_tc:
            tool_name = tc["function"]["name"]
            tool_args = tc["function"]["arguments"]
            tool_call_id = tc["id"]

            if approved:
                result_str = self.dispatch_tool_call(
                    tool_name, tool_args, user_id, conversation_id,
                )
            else:
                result_str = json.dumps({
                    "tool_used": tool_name,
                    "status": "rejected",
                    "message": "User declined to execute this action.",
                })

            self._save_message(
                conversation_id,
                "tool",
                content=result_str,
                tool_call_id=tool_call_id,
            )

            yield f"event: tool_result\ndata: {json.dumps({'tool_call_id': tool_call_id, 'name': tool_name, 'result': result_str})}\n\n"

        # Reload context and continue the agent loop
        memory_context = self._load_session_context(user_id)
        bootstrap_context = ""
        try:
            bootstrap_context = load_bootstrap_files(user_id)
        except Exception:
            log.exception("load_bootstrap_files failed during resume user=%s", user_id)
        skills_context = None
        try:
            skills_context = load_skills_for_prompt(user_id)
        except Exception:
            pass

        yield from self._run_agent_loop(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message="",
            forced_skill=None,
            memory_context=memory_context,
            retrieved_context="",
            workflow_context="",
            skills_context=skills_context,
            bootstrap_context=bootstrap_context,
            rag_sources=[],
        )

    # ── Session / persistence ──────────────────────────────────────

    @staticmethod
    def _save_message(conversation_id: str, role: str, **kwargs) -> dict:
        """Insert a message row and return it."""
        sb = get_supabase()
        data = {"conversation_id": conversation_id, "role": role}
        data.update({k: v for k, v in kwargs.items() if v is not None})
        result = sb.table("messages").insert(data).execute()
        return result.data[0]

    @staticmethod
    def _get_history(conversation_id: str) -> list[dict]:
        """Fetch messages within the context window (last N hours)."""
        sb = get_supabase()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=Config.CHAT_HISTORY_HOURS)).isoformat()
        result = (
            sb.table("messages")
            .select("*")
            .eq("conversation_id", conversation_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data

    @staticmethod
    def _is_first_exchange(conversation_id: str) -> bool:
        """True if only one user message exists in this conversation."""
        sb = get_supabase()
        result = (
            sb.table("messages")
            .select("id")
            .eq("conversation_id", conversation_id)
            .eq("role", "user")
            .execute()
        )
        return len(result.data) == 1

    @staticmethod
    def _update_title(conversation_id: str, user_id: str, user_msg: str, assistant_msg: str):
        """Generate and set a conversation title after the first exchange."""
        title = generate_title(user_msg, assistant_msg)
        sb = get_supabase()
        sb.table("conversations").update({"title": title}).eq("id", conversation_id).eq("user_id", user_id).execute()

    # ── Context assembly ───────────────────────────────────────────

    @staticmethod
    def _load_session_context(user_id: str) -> str:
        """Create today's daily file (idempotent), ensure bootstrap
        templates exist, and return recent daily context."""
        memory_context = ""
        try:
            ensure_daily_file(user_id)
        except Exception:
            log.exception("ensure_daily_file failed for user=%s", user_id)
        try:
            ensure_bootstrap_files(user_id)
        except Exception:
            log.exception("ensure_bootstrap_files failed for user=%s", user_id)
        try:
            ensure_default_onboarding_skill(user_id)
        except Exception:
            log.exception("ensure_default_onboarding_skill failed for user=%s", user_id)
        try:
            memory_context = get_session_context(user_id)
        except Exception:
            log.exception("get_session_context failed for user=%s", user_id)
        return memory_context

    @staticmethod
    def _is_skill_already_loaded(history: list[dict], skill_name: str) -> bool:
        """Return True once skill_read has been called for the forced skill."""
        for msg in history:
            if msg.get("role") != "assistant":
                continue
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                if fn.get("name") != "skill_read":
                    continue
                args_raw = fn.get("arguments")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except Exception:
                    args = {}
                if args.get("skill_name") == skill_name:
                    return True
        return False

    @staticmethod
    def _retrieve_context(user_id: str, query: str) -> tuple[str, list[dict]]:
        """Run RAG retrieval and return (context_text, source_refs)."""
        retrieved_context = ""
        rag_sources: list[dict] = []
        try:
            today = date.today()
            yesterday = today - timedelta(days=1)
            skip_files = {
                f"daily/{today.isoformat()}.md",
                f"daily/{yesterday.isoformat()}.md",
            }

            rag_results = hybrid_search(user_id, query, Config.RAG_RESULT_LIMIT)

            filtered = [
                r for r in rag_results
                if r["source_file"] not in skip_files
                and r.get("score", 0) >= Config.RAG_MIN_SCORE
            ]

            if filtered:
                parts = []
                seen_sources: set[str] = set()
                for r in filtered:
                    parts.append(f"<source: {r['source_file']}>\n{r['chunk_text']}")
                    if r["source_file"] not in seen_sources:
                        seen_sources.add(r["source_file"])
                        rag_sources.append({
                            "source_file": r["source_file"],
                            "score": round(r.get("score", 0), 4),
                        })
                retrieved_context = "\n\n".join(parts)
        except Exception:
            log.exception("RAG retrieval failed for user=%s", user_id)
        return retrieved_context, rag_sources

    # ── Pre-compaction flush ───────────────────────────────────────

    def _run_silent_flush(self, conversation_id: str, memory_context: str) -> None:
        """Silent flush turn: ask the model to persist durable facts via memory tools."""
        g.conversation_id = conversation_id

        history = self._get_history(conversation_id)
        messages = build_messages(
            history,
            memory_context=memory_context,
            history_hours=Config.CHAT_HISTORY_HOURS,
        )

        tool_calls = run_flush_completion(messages)
        if not tool_calls:
            return

        self._save_message(
            conversation_id,
            "assistant",
            tool_calls=tool_calls,
            model=Config.OPENAI_MODEL,
        )

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tool_args = tc["function"]["arguments"]
            tool_call_id = tc["id"]

            result_str = tool_registry.execute(tool_name, tool_args)

            self._save_message(
                conversation_id,
                "tool",
                content=result_str,
                tool_call_id=tool_call_id,
            )

    # ── Source tracking ────────────────────────────────────────────

    @staticmethod
    def _collect_tool_sources(
        tool_name: str,
        tool_args: str | dict,
        result_str: str,
        all_sources: list[dict],
        seen_source_files: set[str],
    ) -> None:
        """Extract document/memory source references from tool calls."""
        try:
            args = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
        except (json.JSONDecodeError, TypeError):
            args = {}

        new_sources: list[str] = []

        if tool_name == "document_read":
            filename = args.get("filename", "")
            if filename:
                new_sources.append(f"documents/{filename}")
        elif tool_name == "memory_read":
            date_str = args.get("date")
            if date_str:
                new_sources.append(f"daily/{date_str}.md")
            else:
                new_sources.append(f"daily/{date.today().isoformat()}.md")
        elif tool_name == "memory_search":
            try:
                result_data = json.loads(result_str) if isinstance(result_str, str) else result_str
                for r in result_data.get("results", []):
                    sf = r.get("source_file", "")
                    if sf:
                        new_sources.append(sf)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
        elif tool_name in ("accounting_list_accounts", "accounting_search_transactions"):
            new_sources.append("accounting/integration")
        elif tool_name.startswith("gmail_"):
            new_sources.append("gmail/integration")

        for sf in new_sources:
            if sf not in seen_source_files:
                seen_source_files.add(sf)
                all_sources.append({"source_file": sf, "score": 1.0})

    # ── Tool dispatch ──────────────────────────────────────────────

    def dispatch_tool_call(
        self,
        tool_name: str,
        tool_args: str | dict,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        """Route a tool call to the appropriate executor.

        Single choke-point for rate limiting, audit logging, A/B routing.
        """
        log.debug("dispatch tool=%s args=%s user=%s", tool_name, tool_args, user_id)

        parsed_args = _parse_args(tool_args)
        dispatch_msg, complete_fn = _describe_tool(tool_name, parsed_args)

        publish_event(user_id, {
            "type": "tool_dispatch",
            "actor": "gateway",
            "tool_name": tool_name,
            "message": dispatch_msg,
        })
        try:
            result = tool_registry.execute(tool_name, tool_args)
            log.debug("tool=%s completed (%d chars)", tool_name, len(result) if result else 0)
            publish_event(user_id, {
                "type": "tool_complete",
                "actor": "gateway",
                "tool_name": tool_name,
                "message": complete_fn(result),
            })
            return result
        except Exception as exc:
            log.exception("tool=%s raised an exception", tool_name)
            publish_event(user_id, {
                "type": "tool_error",
                "actor": "gateway",
                "tool_name": tool_name,
                "message": f"{tool_name} failed: {exc}",
            })
            raise

    # ── Workflow context helpers ────────────────────────────────────

    def build_workflow_context(self, user_id: str) -> str | None:
        """System-message block describing pending approvals and active workflows."""
        parts: list[str] = []

        try:
            pending = get_pending_approvals(user_id)
            if pending:
                lines = ["[Pending Workflow Approvals]"]
                for p in pending:
                    tpl = p.get("workflow_templates") or {}
                    name = tpl.get("name", "unknown")
                    steps = tpl.get("steps") or []
                    idx = p.get("current_step_index", 0)
                    prompt = ""
                    if idx < len(steps):
                        approval = steps[idx].get("approval") or {}
                        prompt = approval.get("prompt", "")
                    lines.append(
                        f"- Workflow '{name}' (run {p['id']}) awaits approval: {prompt}"
                    )
                parts.append("\n".join(lines))
        except Exception:
            log.exception("get_pending_approvals failed for user=%s", user_id)

        try:
            active = get_active_workflows(user_id)
            running = [w for w in active if w["status"] == "running"]
            if running:
                lines = ["[Running Workflows]"]
                for w in running:
                    tpl = w.get("workflow_templates") or {}
                    name = tpl.get("name", "unknown")
                    lines.append(f"- '{name}' (run {w['id']}) — step {w.get('current_step_index', '?')}")
                parts.append("\n".join(lines))
        except Exception:
            log.exception("get_active_workflows failed for user=%s", user_id)

        return "\n\n".join(parts) if parts else None

    @staticmethod
    def build_workflow_events(run: dict) -> list[dict]:
        """Convert a workflow run dict into structured SSE event payloads."""
        events: list[dict] = []
        tpl = run.get("workflow_templates") or {}

        if run["status"] in ("pending", "running"):
            events.append({
                "type": "workflow_started",
                "run_id": run["id"],
                "workflow": tpl.get("name", "unknown"),
                "status": run["status"],
            })

        if run["status"] == "paused":
            steps = tpl.get("steps") or []
            idx = run.get("current_step_index", 0)
            prompt = ""
            if idx < len(steps):
                approval = steps[idx].get("approval") or {}
                prompt = approval.get("prompt", "Approve this step?")
            events.append({
                "type": "workflow_approval_needed",
                "run_id": run["id"],
                "workflow": tpl.get("name", "unknown"),
                "prompt": prompt,
                "resume_token": run.get("resume_token"),
            })

        if run["status"] == "completed":
            events.append({
                "type": "workflow_completed",
                "run_id": run["id"],
                "workflow": tpl.get("name", "unknown"),
                "steps_state": run.get("steps_state"),
            })

        if run["status"] == "failed":
            events.append({
                "type": "workflow_failed",
                "run_id": run["id"],
                "workflow": tpl.get("name", "unknown"),
                "error": run.get("error"),
            })

        return events


# Module-level singleton
gateway = Gateway()

# Backwards-compatible top-level aliases for any external callers
dispatch_tool_call = gateway.dispatch_tool_call
build_workflow_context = gateway.build_workflow_context
build_workflow_events = Gateway.build_workflow_events
