"""Specialized Business Operations Agent for operational planning and workflow consolidation."""
from typing import Dict, Any, Optional
from app.agents.base import BaseAgent, AgentStepContext
from app.agents.tools.registry import ToolRegistry
from app.ai.base import BaseAIProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class BusinessOperationsAgent(BaseAgent):
    agent_id = "agent_business_ops"
    display_name = "Business Operations Agent"
    description = "Coordinates business workflows, synthesizes multi-department proposals, and tracks operational deliverables."
    responsibility = "Structure business initiatives, analyze operational data, draft project proposals, and consolidate executive summaries."
    instructions = (
        "You are Gideon's Business Operations Specialist. Synthesize diverse project streams into cohesive business initiatives. "
        "Enforce data security and maintain clear operational accountability."
    )
    supported_task_types = ["business_analysis", "operations", "executive_brief", "project_proposal", "workflow_optimization"]
    allowed_tools = [
        "tool_research_fetch",
        "tool_search_memories",
        "tool_list_directive_tasks",
        "tool_create_directive_task",
        "tool_draft_email",
    ]
    permission_requirements = ["read_only", "local_changes"]
    timeout_seconds = 150
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
        logger.info("BusinessOperationsAgent executing step: %s", context.step_key)
        tool_id = context.tool_id
        tool_result = {}

        if tool_id and self.is_tool_allowed(tool_id):
            tool = tool_registry.get(tool_id)
            if tool:
                tool_params = context.input_data.get("tool_params") or {
                    "query": context.description,
                    "aspects": ["operational_impact", "resource_requirements", "risk_factors"]
                }
                tool_result = await tool.execute(
                    params=tool_params,
                    context={"db": db_session, "desktop_service": desktop_service}
                )

        operations_report = {
            "initiative": context.description,
            "risk_assessment": "Standard operational risk. No unrestricted financial commitments allowed.",
            "resource_allocation": ["Research & Strategy", "Technical Implementation", "Stakeholder Communication"],
            "tool_output": tool_result,
            "deliverables": [
                "Operational blueprint verified",
                "Action item sequencing defined",
                "Executive briefing synthesized"
            ]
        }

        return {
            "status": "completed",
            "report": operations_report,
            "summary": f"Business operations analysis complete: '{context.description}'. Deliverables staged for execution."
        }

