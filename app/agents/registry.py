"""Central Agent Registry defining available specialized agents and capabilities."""
from typing import Dict, List, Optional
from app.agents.base import BaseAgent
from app.agents.specialized.research import ResearchAgent
from app.agents.specialized.productivity import ProductivityAgent
from app.agents.specialized.coding import CodingAgent
from app.agents.specialized.marketing import MarketingAgent
from app.agents.specialized.email_assistant import EmailAssistantAgent
from app.agents.specialized.business_ops import BusinessOperationsAgent
from app.schemas.agent import AgentDefinitionRead


class AgentRegistry:
    """Central registry maintaining all verified specialized agents in Gideon."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._register_default_agents()

    def _register_default_agents(self):
        defaults: List[BaseAgent] = [
            ResearchAgent(),
            ProductivityAgent(),
            CodingAgent(),
            MarketingAgent(),
            EmailAssistantAgent(),
            BusinessOperationsAgent(),
        ]
        for agent in defaults:
            self.register(agent)

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[AgentDefinitionRead]:
        return [agent.to_definition_read() for agent in self._agents.values()]

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def is_enabled(self, agent_id: str) -> bool:
        agent = self.get(agent_id)
        return agent is not None and agent.enabled

    def find_agent_for_task_type(self, task_type: str) -> Optional[BaseAgent]:
        """Find an enabled agent that explicitly supports the given task type."""
        for agent in self._agents.values():
            if agent.enabled and task_type in agent.supported_task_types:
                return agent
        return None

