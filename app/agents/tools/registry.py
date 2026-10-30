"""Centralized Tool Registry for Gideon Agent Tools."""
from typing import Dict, List, Optional
from app.agents.tools.base import BaseTool
from app.agents.tools.builtins import (
    WorkspaceListFilesTool,
    WorkspaceReadFileTool,
    WorkspaceProposeDiffTool,
    ListDirectiveTasksTool,
    CreateDirectiveTaskTool,
    SearchMemoriesTool,
    ResearchFetchTool,
    DraftEmailTool,
    SendEmailTool,
    DesktopActionTool,
    LocalScreenAwarenessTool,
    LocalFolderSummaryTool,
)
from app.schemas.agent import ToolDefinitionRead


class ToolRegistry:
    """Registry maintaining all approved tools and enforcing permission policies."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        default_tools: List[BaseTool] = [
            WorkspaceListFilesTool(),
            WorkspaceReadFileTool(),
            WorkspaceProposeDiffTool(),
            ListDirectiveTasksTool(),
            CreateDirectiveTaskTool(),
            SearchMemoriesTool(),
            ResearchFetchTool(),
            DraftEmailTool(),
            SendEmailTool(),
            DesktopActionTool(),
            LocalScreenAwarenessTool(),
            LocalFolderSummaryTool(),
        ]
        for tool in default_tools:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> Optional[BaseTool]:
        return self._tools.get(tool_id)

    def list_tools(self) -> List[ToolDefinitionRead]:
        return [tool.to_definition_read() for tool in self._tools.values()]

    def is_registered(self, tool_id: str) -> bool:
        return tool_id in self._tools
