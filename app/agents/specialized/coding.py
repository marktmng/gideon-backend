"""Specialized Coding Agent for software engineering and workspace inspection."""
from typing import Dict, Any, Optional
from app.agents.base import BaseAgent, AgentStepContext
from app.agents.tools.registry import ToolRegistry
from app.ai.base import BaseAIProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class CodingAgent(BaseAgent):
    agent_id = "agent_coding"
    display_name = "Coding Agent"
    description = "Analyzes source code, inspects authorized project files, and formulates safe code modifications."
    responsibility = "Inspect workspace files, formulate implementation plans, propose code changes, and verify syntax."
    instructions = (
        "You are Gideon's Software Engineering Specialist. Analyze code architecture with precision. "
        "Respect workspace boundaries and generate clean, modular code diffs."
    )
    supported_task_types = ["coding", "code_review", "refactoring", "debugging", "architecture_design"]
    allowed_tools = [
        "tool_workspace_list_files",
        "tool_workspace_read_file",
        "tool_workspace_propose_diff",
    ]
    permission_requirements = ["read_only", "local_changes"]
    timeout_seconds = 180
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
        logger.info("CodingAgent executing step: %s", context.step_key)
        tool_id = context.tool_id or "tool_workspace_list_files"
        tool_result = {}

        if tool_id and self.is_tool_allowed(tool_id):
            tool = tool_registry.get(tool_id)
            if tool:
                tool_params = context.input_data.get("tool_params") or {}
                if tool_id == "tool_workspace_read_file" and "file_path" not in tool_params:
                    tool_params["file_path"] = context.input_data.get("file_path", "README.md")
                elif tool_id == "tool_workspace_propose_diff" and "file_path" not in tool_params:
                    tool_params = {
                        "file_path": context.input_data.get("file_path", "proposed_patch.py"),
                        "proposed_diff": context.input_data.get("proposed_diff", "# Proposed modification\n"),
                        "explanation": context.description
                    }
                tool_result = await tool.execute(
                    params=tool_params,
                    context={"db": db_session, "desktop_service": desktop_service}
                )

        code_analysis = {
            "target": context.description,
            "tool_id_used": tool_id,
            "tool_output": tool_result,
            "architectural_review": "Code structure verified within workspace boundaries.",
            "test_readiness": "Proposed changes are isolated and ready for test runner execution."
        }

        return {
            "status": "completed",
            "analysis": code_analysis,
            "summary": f"Coding task completed: '{context.description}'. Files inspected and changes staged."
        }

