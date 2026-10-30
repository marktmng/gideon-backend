"""Unit tests for Gideon Agent Registry and Agent specifications."""
import pytest
from app.agents.registry import AgentRegistry
from app.agents.base import BaseAgent


def test_agent_registry_contains_all_initial_agents():
    registry = AgentRegistry()
    agents = registry.list_agents()
    agent_ids = {a.agent_id for a in agents}

    expected_ids = {
        "agent_research",
        "agent_productivity",
        "agent_coding",
        "agent_marketing",
        "agent_email",
        "agent_business_ops",
    }
    assert expected_ids.issubset(agent_ids)
    assert len(agents) >= 6


def test_agent_registry_get_and_properties():
    registry = AgentRegistry()
    research = registry.get("agent_research")
    assert research is not None
    assert research.display_name == "Research Agent"
    assert "tool_research_fetch" in research.allowed_tools
    assert "tool_workspace_read_file" in research.allowed_tools

    # Validate that arbitrary tools are forbidden
    assert research.is_tool_allowed("tool_send_email") is False
    assert research.is_tool_allowed("unregistered_arbitrary_tool") is False


def test_coding_agent_permissions():
    registry = AgentRegistry()
    coding = registry.get("agent_coding")
    assert coding is not None
    assert "tool_workspace_propose_diff" in coding.allowed_tools
    assert "tool_send_email" not in coding.allowed_tools


def test_email_agent_requires_consequential_approval():
    registry = AgentRegistry()
    email_agent = registry.get("agent_email")
    assert email_agent is not None
    assert "consequential" in email_agent.permission_requirements
    assert "tool_send_email" in email_agent.allowed_tools


def test_find_agent_for_task_type():
    registry = AgentRegistry()
    assert registry.find_agent_for_task_type("coding").agent_id == "agent_coding"
    assert registry.find_agent_for_task_type("research").agent_id == "agent_research"
    assert registry.find_agent_for_task_type("email_draft").agent_id == "agent_email"
    assert registry.find_agent_for_task_type("planning").agent_id == "agent_productivity"


def test_disabled_agent_cannot_be_active():
    registry = AgentRegistry()
    agent = registry.get("agent_research")
    agent.enabled = False
    assert registry.is_enabled("agent_research") is False
    # Reset
    agent.enabled = True
    assert registry.is_enabled("agent_research") is True

