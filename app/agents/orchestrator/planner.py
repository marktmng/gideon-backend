"""Task Planner with graph dependency validation, cycle detection, and agent matching."""
import re
from typing import List, Dict, Any, Optional
from app.agents.registry import AgentRegistry
from app.agents.tools.registry import ToolRegistry
from app.schemas.agent import AgentPlan, AgentStepCreate, ToolPermissionLevel
from app.core.logging import get_logger

logger = get_logger(__name__)


class TaskPlanValidationError(Exception):
    """Raised when a proposed plan fails validation or contains dependency cycles."""
    pass


class TaskPlanner:
    """Creates and rigorously validates multi-step agent plans."""

    def __init__(self, agent_registry: AgentRegistry, tool_registry: ToolRegistry):
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry

    def create_plan(
        self,
        user_request: str,
        preferred_agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentPlan:
        """
        Decompose a user request into a validated multi-step plan.
        Employs structured deterministic routing and decomposition.
        """
        req_lower = user_request.lower()

        # 1. Determine primary agent if not explicitly requested
        target_agent = preferred_agent_id
        if not target_agent or not self.agent_registry.is_registered(target_agent):
            if any(k in req_lower for k in ["code", "python", "javascript", "function", "bug", "refactor", "file", "directory", "script"]):
                target_agent = "agent_coding"
            elif any(k in req_lower for k in ["email", "reply", "send to", "draft message", "recipient"]):
                target_agent = "agent_email"
            elif any(k in req_lower for k in ["research", "investigate", "survey", "find out", "who is", "what is"]):
                target_agent = "agent_research"
            elif any(k in req_lower for k in ["marketing", "campaign", "audience", "outreach", "ad copy"]):
                target_agent = "agent_marketing"
            elif any(k in req_lower for k in ["task", "todo", "checklist", "priority", "schedule", "plan"]):
                target_agent = "agent_productivity"
            else:
                target_agent = "agent_business_ops"

        steps: List[AgentStepCreate] = []

        # 2. Formulate steps based on domain
        if target_agent == "agent_coding":
            steps = [
                AgentStepCreate(
                    step_key="step_1_inspect_workspace",
                    step_order=1,
                    description=f"Inspect workspace files relevant to: '{user_request}'",
                    assigned_agent_id="agent_coding",
                    tool_id="tool_workspace_list_files",
                    input_data={"subpath": ""},
                    dependencies=[],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_2_read_and_analyze",
                    step_order=2,
                    description=f"Read target source file and analyze code logic",
                    assigned_agent_id="agent_coding",
                    tool_id="tool_workspace_read_file",
                    input_data={"file_path": "README.md"},
                    dependencies=["step_1_inspect_workspace"],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_3_propose_solution",
                    step_order=3,
                    description=f"Propose code implementation for '{user_request}'",
                    assigned_agent_id="agent_coding",
                    tool_id="tool_workspace_propose_diff",
                    input_data={"file_path": "proposed_solution.py", "proposed_diff": f"# Solution for {user_request}\n", "explanation": "Implemented requested code change."},
                    dependencies=["step_2_read_and_analyze"],
                    requires_approval=False,
                ),
            ]
        elif target_agent == "agent_email":
            # Extract possible recipient
            email_match = re.search(r"[\w\.-]+@[\w\.-]+", user_request)
            recipient = email_match.group(0) if email_match else "recipient@example.com"
            steps = [
                AgentStepCreate(
                    step_key="step_1_draft_correspondence",
                    step_order=1,
                    description=f"Draft email regarding: '{user_request}'",
                    assigned_agent_id="agent_email",
                    tool_id="tool_draft_email",
                    input_data={"tool_params": {"recipient": recipient, "subject": f"Notice: {user_request[:40]}", "body": f"Regarding: {user_request}"}},
                    dependencies=[],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_2_send_approved_email",
                    step_order=2,
                    description=f"Send email to '{recipient}' after explicit user authorization",
                    assigned_agent_id="agent_email",
                    tool_id="tool_send_email",
                    input_data={"tool_params": {"recipient": recipient, "subject": f"Notice: {user_request[:40]}", "body": f"Regarding: {user_request}"}},
                    dependencies=["step_1_draft_correspondence"],
                    requires_approval=True,  # Consequential action
                ),
            ]
        elif target_agent == "agent_research":
            steps = [
                AgentStepCreate(
                    step_key="step_1_gather_evidence",
                    step_order=1,
                    description=f"Gather evidence on: '{user_request}'",
                    assigned_agent_id="agent_research",
                    tool_id="tool_research_fetch",
                    input_data={"tool_params": {"query": user_request, "aspects": ["core_facts", "evidence", "assumptions"]}},
                    dependencies=[],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_2_synthesize_findings",
                    step_order=2,
                    description=f"Synthesize structured findings and document source credibility",
                    assigned_agent_id="agent_research",
                    tool_id="tool_search_memories",
                    input_data={"tool_params": {"query": user_request}},
                    dependencies=["step_1_gather_evidence"],
                    requires_approval=False,
                ),
            ]
        elif target_agent == "agent_productivity":
            steps = [
                AgentStepCreate(
                    step_key="step_1_decompose_tasks",
                    step_order=1,
                    description=f"Decompose initiative into prioritized action items: '{user_request}'",
                    assigned_agent_id="agent_productivity",
                    tool_id="tool_list_directive_tasks",
                    input_data={"tool_params": {"limit": 10}},
                    dependencies=[],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_2_persist_directive",
                    step_order=2,
                    description=f"Record verified action items into Gideon persistent task tracking",
                    assigned_agent_id="agent_productivity",
                    tool_id="tool_create_directive_task",
                    input_data={"tool_params": {"title": user_request[:80], "description": user_request, "priority": "medium"}},
                    dependencies=["step_1_decompose_tasks"],
                    requires_approval=False,
                ),
            ]
        elif target_agent == "agent_marketing":
            steps = [
                AgentStepCreate(
                    step_key="step_1_analyze_opportunity",
                    step_order=1,
                    description=f"Research market angles for: '{user_request}'",
                    assigned_agent_id="agent_marketing",
                    tool_id="tool_research_fetch",
                    input_data={"tool_params": {"query": user_request}},
                    dependencies=[],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_2_draft_campaign_content",
                    step_order=2,
                    description=f"Prepare campaign proposal and draft outreach copy",
                    assigned_agent_id="agent_marketing",
                    tool_id="tool_draft_email",
                    input_data={"tool_params": {"recipient": "marketing-leads@example.com", "subject": f"Campaign: {user_request[:30]}", "body": f"Proposed campaign copy for {user_request}"}},
                    dependencies=["step_1_analyze_opportunity"],
                    requires_approval=False,
                ),
            ]
        else:  # Business Operations default
            steps = [
                AgentStepCreate(
                    step_key="step_1_operational_assessment",
                    step_order=1,
                    description=f"Perform operational risk and resource analysis for '{user_request}'",
                    assigned_agent_id="agent_business_ops",
                    tool_id="tool_research_fetch",
                    input_data={"tool_params": {"query": user_request}},
                    dependencies=[],
                    requires_approval=False,
                ),
                AgentStepCreate(
                    step_key="step_2_sequence_deliverables",
                    step_order=2,
                    description=f"Sequence deliverables and schedule action items",
                    assigned_agent_id="agent_productivity",
                    tool_id="tool_create_directive_task",
                    input_data={"tool_params": {"title": f"Business Ops: {user_request[:50]}", "description": user_request, "priority": "high"}},
                    dependencies=["step_1_operational_assessment"],
                    requires_approval=False,
                ),
            ]

        plan = AgentPlan(goal=user_request, steps=steps)
        self.validate_plan(plan)
        return plan

    def validate_plan(self, plan: AgentPlan) -> None:
        """
        Validate plan integrity:
        - Must contain between 1 and 15 steps.
        - All assigned agents must be registered and enabled.
        - All specified tools must be registered and authorized for that agent.
        - Check for dependency cycles using Kahn's algorithm / topological sort.
        - Enforce approval flags for consequential tools.
        """
        if not plan.steps:
            raise TaskPlanValidationError("Plan must contain at least one execution step.")
        if len(plan.steps) > 15:
            raise TaskPlanValidationError(f"Plan exceeds maximum allowed steps (15). Proposed: {len(plan.steps)}")

        step_keys = set()
        adj: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        for step in plan.steps:
            if step.step_key in step_keys:
                raise TaskPlanValidationError(f"Duplicate step key '{step.step_key}' in plan.")
            step_keys.add(step.step_key)
            adj[step.step_key] = []
            in_degree[step.step_key] = 0

            # Validate agent
            if not self.agent_registry.is_registered(step.assigned_agent_id):
                raise TaskPlanValidationError(f"Agent '{step.assigned_agent_id}' is not registered.")
            if not self.agent_registry.is_enabled(step.assigned_agent_id):
                raise TaskPlanValidationError(f"Agent '{step.assigned_agent_id}' is currently disabled.")

            agent = self.agent_registry.get(step.assigned_agent_id)

            # Validate tool permissions
            if step.tool_id:
                if not self.tool_registry.is_registered(step.tool_id):
                    raise TaskPlanValidationError(f"Tool '{step.tool_id}' is not registered.")
                if not agent.is_tool_allowed(step.tool_id):
                    raise TaskPlanValidationError(
                        f"Agent '{step.assigned_agent_id}' is not permitted to use tool '{step.tool_id}'."
                    )
                tool = self.tool_registry.get(step.tool_id)
                if tool.requires_approval or tool.permission_level == ToolPermissionLevel.consequential:
                    step.requires_approval = True

        # Validate dependencies & detect cycles
        for step in plan.steps:
            for dep in step.dependencies:
                if dep not in step_keys:
                    raise TaskPlanValidationError(f"Step '{step.step_key}' depends on non-existent step '{dep}'.")
                if dep == step.step_key:
                    raise TaskPlanValidationError(f"Step '{step.step_key}' cannot depend on itself.")
                adj[dep].append(step.step_key)
                in_degree[step.step_key] += 1

        # Cycle detection via Kahn's algorithm
        queue = [k for k, deg in in_degree.items() if deg == 0]
        visited_count = 0
        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(step_keys):
            raise TaskPlanValidationError("Plan contains a cyclic dependency loop between steps.")

