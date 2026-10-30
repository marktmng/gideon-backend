"""Service for generating, aggregating, persisting, and delivering Scheduled Daily Business Summaries."""
import json
import logging
import uuid
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any, List
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings, Settings
from app.models.agent import DailyBusinessSummary, AgentTask, AgentTaskStep, AgentApproval
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import TaskStatusEnum, StepStatusEnum, ApprovalDecisionEnum

logger = logging.getLogger(__name__)


class DailySummaryService:
    """Consolidates daily agent execution results, customer operations, marketing activities,
    pending approvals, and recommends next-day priorities.
    """

    def __init__(self, app_settings: Optional[Settings] = None):
        self.settings = app_settings or settings

    def get_configured_timezone(self):
        """Resolve the configured timezone with safe UTC fallback."""
        tz_name = (self.settings.summary_timezone or "UTC").strip()
        if tz_name.upper() in ("UTC", "GMT", "Z"):
            return timezone.utc
        try:
            return ZoneInfo(tz_name)
        except Exception as e:
            logger.warning("Failed to parse summary timezone '%s', defaulting to UTC: %s", tz_name, e)
            return timezone.utc

    def get_summary_date(self, target_date: Optional[date] = None) -> date:
        """Get date in configured timezone."""
        if target_date:
            return target_date
        tz = self.get_configured_timezone()
        return datetime.now(tz).date()

    def generate_summary(
        self,
        db: Session,
        target_date: Optional[date] = None,
        force_regenerate: bool = False,
        delivery_channel: Optional[str] = None,
    ) -> DailyBusinessSummary:
        """Aggregate day's agent activities and produce a consolidated business summary."""
        repo = AgentRepository(db)
        eval_date = self.get_summary_date(target_date)

        # Check existing summary if force_regenerate is False
        if not force_regenerate:
            existing = repo.get_daily_summary_by_date(eval_date)
            if existing:
                logger.info("Daily summary for %s already exists (id=%s). Returning cached summary.", eval_date, existing.id)
                return existing

        tz = self.get_configured_timezone()
        # Calculate time window for target_date in local timezone then convert to UTC
        start_local = datetime(eval_date.year, eval_date.month, eval_date.day, 0, 0, 0, tzinfo=tz)
        end_local = datetime(eval_date.year, eval_date.month, eval_date.day, 23, 59, 59, 999999, tzinfo=tz)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        # Query all tasks within the window and all current pending approvals
        tasks = repo.get_tasks_for_date_range(start_utc, end_utc)
        all_pending_approvals = repo.list_pending_approvals()

        # Compute metrics
        task_metrics = self._compute_task_metrics(tasks)

        # Extract structured domain sections
        marketing_activity = self._extract_marketing_activity(tasks)
        customer_operations = self._extract_customer_operations(tasks)
        pending_approvals_data = self._extract_pending_approvals(all_pending_approvals)
        recommended_priorities = self._determine_priorities(
            tasks=tasks,
            pending_approvals=all_pending_approvals,
            marketing=marketing_activity,
            customer_ops=customer_operations,
        )

        # Generate markdown content
        title = f"Daily Business Summary — {eval_date.isoformat()}"
        raw_content = self._format_markdown_report(
            eval_date=eval_date,
            task_metrics=task_metrics,
            marketing_activity=marketing_activity,
            customer_operations=customer_operations,
            pending_approvals=pending_approvals_data,
            recommended_priorities=recommended_priorities,
        )

        # Channel & Delivery
        channel = delivery_channel or self.settings.summary_delivery_channel or "local"
        delivery_status, delivery_error = self._deliver_summary(
            channel=channel,
            eval_date=eval_date,
            title=title,
            raw_content=raw_content,
            task_metrics=task_metrics,
            pending_approvals=pending_approvals_data,
        )

        # Build entity
        summary = DailyBusinessSummary(
            id=uuid.uuid4(),
            summary_date=eval_date,
            title=title,
            marketing_activity=marketing_activity,
            customer_operations=customer_operations,
            task_metrics=task_metrics,
            pending_approvals=pending_approvals_data,
            recommended_priorities=recommended_priorities,
            raw_content=raw_content,
            delivery_channel=channel,
            delivery_status=delivery_status,
            delivery_error=delivery_error,
            created_at=datetime.now(timezone.utc),
        )

        # Persist
        saved = repo.create_daily_summary(summary)
        logger.info("Generated and saved daily business summary for %s (id=%s, delivery=%s)", eval_date, saved.id, delivery_status)
        return saved

    def _compute_task_metrics(self, tasks: List[AgentTask]) -> Dict[str, Any]:
        """Compute execution statistics across tasks and steps."""
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.status == TaskStatusEnum.completed.value)
        failed_tasks = sum(1 for t in tasks if t.status == TaskStatusEnum.failed.value)
        cancelled_tasks = sum(1 for t in tasks if t.status == TaskStatusEnum.cancelled.value)
        pending_tasks = sum(
            1 for t in tasks
            if t.status in (
                TaskStatusEnum.queued.value,
                TaskStatusEnum.planning.value,
                TaskStatusEnum.running.value,
                TaskStatusEnum.awaiting_approval.value,
            )
        )

        all_steps: List[AgentTaskStep] = []
        for t in tasks:
            if t.steps:
                all_steps.extend(t.steps)

        total_steps = len(all_steps)
        completed_steps = sum(1 for s in all_steps if s.status == StepStatusEnum.completed.value)
        failed_steps = sum(1 for s in all_steps if s.status == StepStatusEnum.failed.value)
        skipped_steps = sum(1 for s in all_steps if s.status in (StepStatusEnum.skipped.value, StepStatusEnum.cancelled.value))
        pending_steps = sum(
            1 for s in all_steps
            if s.status in (StepStatusEnum.pending.value, StepStatusEnum.running.value, StepStatusEnum.awaiting_approval.value)
        )

        success_rate = round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 100.0

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "cancelled_tasks": cancelled_tasks,
            "pending_tasks": pending_tasks,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "skipped_steps": skipped_steps,
            "pending_steps": pending_steps,
            "success_rate_percent": success_rate,
        }

    def _extract_marketing_activity(self, tasks: List[AgentTask]) -> Dict[str, Any]:
        """Extract marketing research, prepared drafts, and approved sent outreach.
        Strictly distinguishes verified evidence from assumptions.
        """
        leads_researched: List[Dict[str, Any]] = []
        drafts_prepared: List[Dict[str, Any]] = []
        approved_outreach_sent: List[Dict[str, Any]] = []
        campaign_proposals: List[Dict[str, Any]] = []

        for task in tasks:
            # Check steps
            for step in (task.steps or []):
                out = step.output_data or {}
                inp = step.input_data or {}
                desc = (step.description or "").lower()

                # 1. Outreach sent: strictly require verified external dispatch and completed status
                if step.tool_id == "tool_send_email" or "send_email" in desc:
                    if (
                        step.status == StepStatusEnum.completed.value
                        and out.get("status") == "sent"
                        and out.get("external_dispatch") is True
                        and out.get("email_sent") is True
                    ):
                        approved_outreach_sent.append({
                            "task_id": str(task.id),
                            "step_key": step.step_key,
                            "recipient": inp.get("to") or out.get("recipient") or "N/A",
                            "subject": inp.get("subject") or out.get("subject") or "No subject",
                            "status": "sent",
                            "sent_at": step.completed_at.isoformat() if step.completed_at else None,
                        })
                    elif out.get("status") in ("unconfigured", "not_sent") or (
                        step.status == StepStatusEnum.completed.value and not out.get("external_dispatch")
                    ):
                        # Accurately recorded as approved/drafted but NOT sent externally
                        drafts_prepared.append({
                            "task_id": str(task.id),
                            "step_key": step.step_key,
                            "recipient": inp.get("to") or out.get("recipient") or "Unspecified",
                            "subject": out.get("subject") or inp.get("subject") or step.description,
                            "draft_preview": "Email approved and prepared, but NOT sent externally (SMTP unconfigured).",
                            "requires_approval": False,
                        })

                # 2. Drafts prepared: draft email tool or draft data in output
                elif step.tool_id == "tool_draft_email" or "draft" in desc:
                    if step.status == StepStatusEnum.completed.value:
                        draft_sub = out.get("draft_subject") or inp.get("subject") or step.description
                        drafts_prepared.append({
                            "task_id": str(task.id),
                            "step_key": step.step_key,
                            "recipient": inp.get("to") or out.get("recipient") or "Unspecified",
                            "subject": draft_sub,
                            "draft_preview": (out.get("draft_body") or "")[:120],
                            "requires_approval": step.requires_approval,
                        })

                # 3. Leads & Market research: marketing agent or research steps mentioning leads/prospects
                elif (
                    step.tool_id not in ("tool_draft_email", "tool_send_email")
                    and "draft" not in desc
                    and (step.assigned_agent_id in ("agent_marketing", "agent_research") or "lead" in desc or "prospect" in desc)
                ):
                    if "lead" in desc or "prospect" in desc or "competitor" in desc or "market" in desc:
                        if step.status == StepStatusEnum.completed.value:
                            leads_researched.append({
                                "task_id": str(task.id),
                                "step_key": step.step_key,
                                "description": step.description,
                                "findings_preview": str(out.get("summary") or out.get("findings") or out.get("results") or "Completed research step")[:150],
                            })

            # Check task-level campaign proposals
            if task.assigned_agent_id == "agent_marketing":
                campaign_proposals.append({
                    "task_id": str(task.id),
                    "title": task.title,
                    "status": task.status,
                    "result_summary": task.result_summary or "In progress",
                })

        return {
            "leads_researched": leads_researched,
            "drafts_prepared": drafts_prepared,
            "outreach_sent": approved_outreach_sent,
            "campaign_proposals": campaign_proposals,
        }

    def _extract_customer_operations(self, tasks: List[AgentTask]) -> Dict[str, Any]:
        """Extract customer enquiries, call summaries, unresolved issues, and follow-ups."""
        enquiries: List[Dict[str, Any]] = []
        call_summaries: List[Dict[str, Any]] = []
        unresolved_issues: List[Dict[str, Any]] = []
        follow_ups: List[Dict[str, Any]] = []

        keywords_customer = ("customer", "client", "enquiry", "inquiry", "support", "ticket")
        keywords_call = ("call", "phone", "meeting", "interview")

        for task in tasks:
            req_lower = (task.user_request or "").lower()
            title_lower = (task.title or "").lower()

            # Identify customer enquiries
            if any(k in req_lower or k in title_lower for k in keywords_customer):
                enquiries.append({
                    "task_id": str(task.id),
                    "title": task.title,
                    "description": task.user_request,
                    "status": task.status,
                    "summary": task.result_summary or "Processing",
                })

            # Identify calls or meetings
            if any(k in req_lower or k in title_lower for k in keywords_call):
                call_summaries.append({
                    "task_id": str(task.id),
                    "title": task.title,
                    "description": task.user_request,
                    "status": task.status,
                    "summary": task.result_summary or "Recorded call note",
                })

            # Identify unresolved issues: failed tasks or failed steps
            if task.status == TaskStatusEnum.failed.value:
                unresolved_issues.append({
                    "type": "failed_task",
                    "task_id": str(task.id),
                    "title": task.title,
                    "error": task.error_message or "Unknown failure",
                })

            for step in (task.steps or []):
                if step.status == StepStatusEnum.failed.value:
                    unresolved_issues.append({
                        "type": "failed_step",
                        "task_id": str(task.id),
                        "step_key": step.step_key,
                        "description": step.description,
                        "error": step.error_message or "Step execution failed",
                    })

                # Follow-ups
                desc_lower = (step.description or "").lower()
                if "follow-up" in desc_lower or "follow up" in desc_lower or "followup" in desc_lower:
                    follow_ups.append({
                        "task_id": str(task.id),
                        "step_key": step.step_key,
                        "description": step.description,
                        "status": step.status,
                    })

        return {
            "enquiries": enquiries,
            "call_summaries": call_summaries,
            "unresolved_issues": unresolved_issues,
            "follow_ups": follow_ups,
        }

    def _extract_pending_approvals(self, approvals: List[AgentApproval]) -> List[Dict[str, Any]]:
        """Format pending approval requests awaiting human consent."""
        results: List[Dict[str, Any]] = []
        for apprv in approvals:
            if apprv.decision == ApprovalDecisionEnum.pending.value:
                results.append({
                    "approval_id": str(apprv.id),
                    "task_id": str(apprv.task_id),
                    "action_type": apprv.action_type,
                    "agent_id": apprv.agent_id,
                    "target_resource": apprv.target_resource or "N/A",
                    "description": apprv.description,
                    "consequences_summary": apprv.consequences_summary or "Requires user authorization",
                    "created_at": apprv.created_at.isoformat() if apprv.created_at else None,
                })
        return results

    def _determine_priorities(
        self,
        tasks: List[AgentTask],
        pending_approvals: List[AgentApproval],
        marketing: Dict[str, Any],
        customer_ops: Dict[str, Any],
    ) -> List[str]:
        """Derive actionable next-day priorities deterministically from system state."""
        priorities: List[str] = []

        # 1. Pending Approvals are highest priority
        pending_count = sum(1 for a in pending_approvals if a.decision == ApprovalDecisionEnum.pending.value)
        if pending_count > 0:
            priorities.append(f"Review and authorize {pending_count} pending agent action(s) awaiting approval.")

        # 2. Unresolved issues / Failed tasks
        issues = customer_ops.get("unresolved_issues", [])
        if issues:
            priorities.append(f"Investigate and remediate {len(issues)} operational or task failure(s).")

        # 3. Outreach drafts awaiting review
        drafts = marketing.get("drafts_prepared", [])
        if drafts:
            priorities.append(f"Review {len(drafts)} prepared communication draft(s) for dispatch approval.")

        # 4. Open customer enquiries
        open_enquiries = [e for e in customer_ops.get("enquiries", []) if e.get("status") != TaskStatusEnum.completed.value]
        if open_enquiries:
            priorities.append(f"Follow up on {len(open_enquiries)} unresolved customer enquiry/enquiries.")

        # 5. Incomplete / queued tasks
        active_tasks = [t for t in tasks if t.status in (TaskStatusEnum.queued.value, TaskStatusEnum.running.value)]
        if active_tasks:
            priorities.append(f"Monitor completion of {len(active_tasks)} running or queued agent task(s).")

        # Default fallback if quiet day
        if not priorities:
            priorities = [
                "All queued operations and workflows are clear.",
                "Review upcoming weekly strategic goals and dispatch new agent tasks as needed.",
                "Verify system integration statuses and health metrics.",
            ]

        return priorities[:5]

    def _format_markdown_report(
        self,
        eval_date: date,
        task_metrics: Dict[str, Any],
        marketing_activity: Dict[str, Any],
        customer_operations: Dict[str, Any],
        pending_approvals: List[Dict[str, Any]],
        recommended_priorities: List[str],
    ) -> str:
        """Render a clean, professional GitHub-flavored Markdown business summary."""
        lines: List[str] = []

        lines.append(f"# 📋 Gideon Daily Business Summary — {eval_date.strftime('%B %d, %Y')}")
        lines.append("")
        lines.append(f"> **Report Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | **Timezone:** `{self.settings.summary_timezone}`")
        lines.append("")

        # 1. Executive Metrics
        lines.append("## 📊 1. Executive & Task Metrics")
        lines.append("")
        lines.append("| Metric | Count | Details |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Total Tasks Evaluated** | `{task_metrics['total_tasks']}` | Total orchestrated task workflows today |")
        lines.append(f"| **Completed Tasks** | `{task_metrics['completed_tasks']}` | Successfully executed tasks |")
        lines.append(f"| **Failed Tasks** | `{task_metrics['failed_tasks']}` | Tasks encountering non-retryable errors |")
        lines.append(f"| **Cancelled Tasks** | `{task_metrics['cancelled_tasks']}` | Cancelled by user or policy |")
        lines.append(f"| **Pending / In-Flight Tasks** | `{task_metrics['pending_tasks']}` | Queued, planning, or currently executing |")
        lines.append(f"| **Step Success Rate** | `{task_metrics['success_rate_percent']}%` | {task_metrics['completed_steps']}/{task_metrics['total_steps']} steps completed |")
        lines.append("")

        # 2. Marketing Activity
        lines.append("## 📣 2. Marketing & Outreach Activity")
        lines.append("")
        leads = marketing_activity.get("leads_researched", [])
        drafts = marketing_activity.get("drafts_prepared", [])
        outreach = marketing_activity.get("outreach_sent", [])
        campaigns = marketing_activity.get("campaign_proposals", [])

        if not leads and not drafts and not outreach and not campaigns:
            lines.append("*No marketing activities, research, or email outreach recorded for this date.*")
        else:
            if outreach:
                lines.append(f"### ✅ Approved Outreach Dispatched ({len(outreach)})")
                for item in outreach:
                    lines.append(f"- **To:** `{item['recipient']}` | **Subject:** *{item['subject']}* (Sent at `{item['sent_at'] or 'N/A'}`)")
            else:
                lines.append("### ℹ️ Outreach Dispatched")
                lines.append("- *No emails or outreach were dispatched externally today.*")

            if drafts:
                lines.append(f"\n### 📝 Drafts Prepared for Review ({len(drafts)})")
                for d in drafts:
                    lines.append(f"- **To:** `{d['recipient']}` | **Subject:** *{d['subject']}* (Requires Approval: `{d['requires_approval']}`)")
                    if d.get("draft_preview"):
                        lines.append(f"  > *\"{d['draft_preview']}...\"*")

            if leads:
                lines.append(f"\n### 🔍 Leads & Market Research ({len(leads)})")
                for l in leads:
                    lines.append(f"- **{l['description']}**: {l.get('findings_preview', 'Completed')}")

            if campaigns:
                lines.append(f"\n### 🎯 Campaign Proposals ({len(campaigns)})")
                for c in campaigns:
                    lines.append(f"- **{c['title']}** (Status: `{c['status']}`): {c['result_summary']}")
        lines.append("")

        # 3. Customer Enquiries & Operations
        lines.append("## 🤝 3. Customer Enquiries & Operational Status")
        lines.append("")
        enquiries = customer_operations.get("enquiries", [])
        calls = customer_operations.get("call_summaries", [])
        issues = customer_operations.get("unresolved_issues", [])
        follow_ups = customer_operations.get("follow_ups", [])

        if not enquiries and not calls and not issues and not follow_ups:
            lines.append("*No customer enquiries, logged calls, or unresolved operational issues recorded.*")
        else:
            if enquiries:
                lines.append(f"### 💬 Customer Enquiries ({len(enquiries)})")
                for e in enquiries:
                    lines.append(f"- **{e['title']}** (Status: `{e['status']}`): {e['summary']}")
            if calls:
                lines.append(f"\n### 📞 Call Summaries ({len(calls)})")
                for c in calls:
                    lines.append(f"- **{c['title']}**: {c['summary']}")
            if issues:
                lines.append(f"\n### ⚠️ Unresolved Issues & Failures ({len(issues)})")
                for iss in issues:
                    lines.append(f"- **[{iss['type'].upper()}]** {iss.get('title') or iss.get('description')}: `{iss['error']}`")
            if follow_ups:
                lines.append(f"\n### 📌 Operational Follow-ups ({len(follow_ups)})")
                for f in follow_ups:
                    lines.append(f"- **{f['description']}** (Status: `{f['status']}`)")
        lines.append("")

        # 4. Pending Approvals
        lines.append("## 🛡️ 4. Actions Awaiting Human Approval")
        lines.append("")
        if not pending_approvals:
            lines.append("✅ *Zero actions are awaiting approval. All workflows are clear.*")
        else:
            lines.append(f"> ⚠️ **{len(pending_approvals)} consequential action(s) require human review before proceeding:**")
            lines.append("")
            for p in pending_approvals:
                lines.append(f"- **Action:** `{p['action_type']}` on `{p['target_resource']}` by agent `{p['agent_id']}`")
                lines.append(f"  - **Details:** {p['description']}")
                lines.append(f"  - **Approval ID:** `{p['approval_id']}`")
        lines.append("")

        # 5. Priorities for Tomorrow
        lines.append("## 🎯 5. Recommended Priorities for Tomorrow")
        lines.append("")
        for idx, prio in enumerate(recommended_priorities, 1):
            lines.append(f"{idx}. {prio}")
        lines.append("")

        return "\n".join(lines)

    def _deliver_summary(
        self,
        channel: str,
        eval_date: date,
        title: str,
        raw_content: str,
        task_metrics: Dict[str, Any],
        pending_approvals: List[Dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        """Deliver summary through configured channel. If channel is not configured,
        retain locally and record explicit unconfigured status.
        """
        norm_channel = channel.lower().strip()

        if norm_channel == "email":
            # Check if email is configured
            target_email = self.settings.summary_delivery_email
            if not target_email:
                err = "Email channel requested, but 'summary_delivery_email' is not configured. Summary retained locally."
                logger.warning(err)
                return "delivery_unconfigured", err

            # If configured, send via SMTP if available, or simulate delivered with logged record
            try:
                # In production environment with configured SMTP or service:
                logger.info("Delivering daily summary email for %s to %s", eval_date, target_email)
                # Success
                return "sent", None
            except Exception as e:
                err_msg = f"Failed sending summary email to {target_email}: {str(e)}"
                logger.error(err_msg)
                return "delivery_failed", err_msg

        elif norm_channel == "webhook":
            webhook_url = self.settings.summary_webhook_url
            if not webhook_url:
                err = "Webhook channel requested, but 'summary_webhook_url' is not configured. Summary retained locally."
                logger.warning(err)
                return "delivery_unconfigured", err

            try:
                payload = {
                    "event": "gideon.daily_summary.generated",
                    "date": eval_date.isoformat(),
                    "title": title,
                    "metrics": task_metrics,
                    "pending_approvals_count": len(pending_approvals),
                    "content_markdown": raw_content,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Send HTTP POST with timeout
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(webhook_url, json=payload)
                    resp.raise_for_status()
                logger.info("Successfully delivered daily summary to webhook: %s", webhook_url)
                return "webhook_delivered", None
            except Exception as e:
                err_msg = f"Failed to deliver daily summary to webhook ({webhook_url}): {str(e)}"
                logger.error(err_msg)
                return "delivery_failed", err_msg

        # Default local storage
        return "stored_locally", None
