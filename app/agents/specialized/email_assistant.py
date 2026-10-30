"""Specialized Email Assistant Agent for communication drafting and approved dispatch."""
from typing import Dict, Any, Optional
from app.agents.base import BaseAgent, AgentStepContext
from app.agents.tools.registry import ToolRegistry
from app.ai.base import BaseAIProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailAssistantAgent(BaseAgent):
    agent_id = "agent_email"
    display_name = "Email Assistant Agent"
    description = "Drafts articulate email communications, reviews recipient details, and requests explicit approval before transmission."
    responsibility = "Draft correspondence, categorize inquiries, prepare recipient batches, and enforce human approval for delivery."
    instructions = (
        "You are Gideon's Communications Specialist. Draft professional correspondence with precision. "
        "Every external dispatch strictly requires human approval. Never send an email autonomously."
    )
    supported_task_types = ["email_draft", "correspondence", "inbox_triage", "newsletter_draft", "reply_generation"]
    allowed_tools = [
        "tool_draft_email",
        "tool_send_email",
        "tool_search_memories",
    ]
    permission_requirements = ["local_changes", "consequential"]
    timeout_seconds = 120
    max_retries = 2
    enabled = True

    async def execute_step(
        self,
        context: AgentStepContext,
        tool_registry: ToolRegistry,
        ai_provider: Optional[BaseAIProvider] = None,
        db_session: Optional[Any] = None,
        desktop_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        logger.info("EmailAssistantAgent executing step: %s", context.step_key)
        tool_id = context.tool_id or "tool_draft_email"
        tool_result = {}

        if tool_id and self.is_tool_allowed(tool_id):
            tool = tool_registry.get(tool_id)
            if tool:
                tool_params = context.input_data.get("tool_params") or {
                    "recipient": context.input_data.get("recipient", "team@example.com"),
                    "subject": f"Update regarding: {context.description[:50]}",
                    "body": f"Greetings,\n\nThis is a communication regarding: {context.description}.\n\nRegards,\nGideon AI Assistant",
                }
                tool_result = await tool.execute(
                    params=tool_params,
                    context={"db": db_session, "desktop_service": desktop_service}
                )

        status = "completed"
        summary = (
            f"Email draft generated for '{tool_result.get('recipient', 'recipient')}'. Ready for user review."
            if tool_id == "tool_draft_email"
            else f"Email operation executed: {tool_result.get('message', 'Processed')}."
        )

        return {
            "status": status,
            "tool_id_used": tool_id,
            "email_data": tool_result,
            "summary": summary
        }

