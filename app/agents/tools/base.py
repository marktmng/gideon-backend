"""Base interfaces and specifications for Gideon Agent Tools."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, Callable
from pydantic import BaseModel, Field
from app.schemas.agent import ToolPermissionLevel, ToolDefinitionRead


class BaseTool(ABC):
    """Abstract interface for all executable tools in Gideon's agent ecosystem."""

    tool_id: str
    name: str
    description: str
    permission_level: ToolPermissionLevel
    requires_approval: bool = False
    supports_concurrency: bool = True
    timeout_seconds: int = 30
    param_schema: Type[BaseModel]

    @abstractmethod
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute tool with validated parameters.

        :param params: Dictionary matching param_schema.
        :param context: Execution context (task_id, agent_id, db session, etc.).
        :return: Structured result dictionary.
        """
        pass

    def validate_params(self, params: Dict[str, Any]) -> BaseModel:
        """Validate input parameters against the Pydantic schema."""
        return self.param_schema.model_validate(params)

    def to_definition_read(self) -> ToolDefinitionRead:
        """Export tool definition for API and registry inspection."""
        return ToolDefinitionRead(
            tool_id=self.tool_id,
            name=self.name,
            description=self.description,
            permission_level=self.permission_level,
            requires_approval=self.requires_approval,
            supports_concurrency=self.supports_concurrency,
            timeout_seconds=self.timeout_seconds,
            parameter_schema=self.param_schema.model_json_schema(),
            output_schema={"type": "object"},
        )

