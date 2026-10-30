"""Base agent abstractions, execution contracts, and definitions."""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.ai.base import BaseAIProvider
from app.agents.tools.registry import ToolRegistry
from app.schemas.agent import AgentDefinitionRead, AgentStatusEnum


class AgentStepContext(BaseModel):
    task_id: str
    step_key: str
    description: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    tool_id: Optional[str] = None
    task_user_request: str
    prior_step_results: Dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class for all specialized agents in Gideon."""

    agent_id: str
    display_name: str
    description: str
    responsibility: str
    instructions: str
    supported_task_types: List[str]
    allowed_tools: List[str]
    permission_requirements: List[str]
    timeout_seconds: int = 120
    max_retries: int = 2
    enabled: bool = True

    def to_definition_read(self) -> AgentDefinitionRead:
        """Convert agent specification to API schema."""
        return AgentDefinitionRead(
            agent_id=self.agent_id,
            display_name=self.display_name,
            description=self.description,
            responsibility=self.responsibility,
            supported_task_types=self.supported_task_types,
            allowed_tools=self.allowed_tools,
            permission_requirements=self.permission_requirements,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            status=AgentStatusEnum.ready if self.enabled else AgentStatusEnum.disabled,
            input_schema={"type": "object", "properties": {"description": {"type": "string"}, "input_data": {"type": "object"}}},
            output_format={"type": "object", "properties": {"status": {"type": "string"}, "result": {"type": "object"}}},
        )

    def is_tool_allowed(self, tool_id: str) -> bool:
        """Validate if tool is explicitly allowlisted for this agent."""
        return tool_id in self.allowed_tools

    @abstractmethod
    async def execute_step(
        self,
        context: AgentStepContext,
        tool_registry: ToolRegistry,
        ai_provider: Optional[BaseAIProvider] = None,
        db_session: Optional[Any] = None,
        desktop_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute an assigned plan step.

        :param context: Step context with inputs and prior step results.
        :param tool_registry: Central registry of approved tools.
        :param ai_provider: Configured AI provider for reasoning or synthesis.
        :param db_session: Active database session for persistent memory/tasks.
        :param desktop_service: Optional desktop service instance for Phase 4 actions.
        :return: Step execution result dictionary.
        """
        pass

