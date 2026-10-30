"""Specialized Marketing Agent for campaign development and content strategy."""
from typing import Dict, Any, Optional
from app.agents.base import BaseAgent, AgentStepContext
from app.agents.tools.registry import ToolRegistry
from app.ai.base import BaseAIProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class MarketingAgent(BaseAgent):
    agent_id = "agent_marketing"
    display_name = "Marketing Agent"
    description = "Develops strategic marketing campaigns, content outlines, audience segmentation, and draft copy."
    responsibility = "Design outreach strategies, outline target audience profiles, draft promotional copy, and structure campaigns."
    instructions = (
        "You are Gideon's Marketing Specialist. Formulate compelling, audience-targeted marketing initiatives. "
        "Never claim to have published or contacted external parties without verified tool confirmation."
    )
    supported_task_types = ["marketing", "campaign_planning", "content_strategy", "audience_research", "copywriting"]
    allowed_tools = [
        "tool_research_fetch",
        "tool_search_memories",
        "tool_draft_email",
    ]
    permission_requirements = ["read_only", "local_changes"]
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
        logger.info("MarketingAgent executing step: %s", context.step_key)
        tool_id = context.tool_id
        tool_result = {}

        if tool_id and self.is_tool_allowed(tool_id):
            tool = tool_registry.get(tool_id)
            if tool:
                tool_params = context.input_data.get("tool_params") or {
                    "query": f"Marketing opportunities for {context.description}",
                    "aspects": ["audience", "value_proposition", "channels"]
                }
                tool_result = await tool.execute(
                    params=tool_params,
                    context={"db": db_session, "desktop_service": desktop_service}
                )

        campaign_plan = {
            "campaign_objective": context.description,
            "target_segments": ["Enterprise Developers", "AI Automation Practitioners", "Tech Enthusiasts"],
            "channels": ["Email Newsletter", "Product Announcements", "Technical Blog"],
            "core_messaging": f"Introducing advanced capabilities for {context.description}",
            "publication_status": "draft_only (Not published externally)",
            "tool_output": tool_result
        }

        return {
            "status": "completed",
            "campaign_plan": campaign_plan,
            "summary": f"Marketing campaign proposal prepared for '{context.description}'. Draft content structured."
        }

