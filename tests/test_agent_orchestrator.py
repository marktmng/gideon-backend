"""Unit tests for Task Planner, Dependency Validation, and Task Orchestrator."""
import pytest
import uuid
import asyncio
from app.agents.registry import AgentRegistry
from app.agents.tools.registry import ToolRegistry
from app.agents.approval.manager import ApprovalManager
from app.agents.events.publisher import ProgressEventPublisher
from app.agents.orchestrator.planner import TaskPlanner, TaskPlanValidationError
from app.agents.orchestrator.engine import TaskOrchestrator
from app.schemas.agent import AgentPlan, AgentStepCreate, TaskStatusEnum, StepStatusEnum
from app.repositories.agent_repository import AgentRepository


def test_planner_creates_valid_plan_for_domains():
    agent_reg = AgentRegistry()
    tool_reg = ToolRegistry()
    planner = TaskPlanner(agent_reg, tool_reg)

    coding_plan = planner.create_plan("Fix bug in python backend API")
    assert len(coding_plan.steps) == 3
    assert coding_plan.steps[0].assigned_agent_id == "agent_coding"

    email_plan = planner.create_plan("Draft an email to client@example.com about project update")
    assert len(email_plan.steps) == 2
    assert email_plan.steps[0].assigned_agent_id == "agent_email"
    assert email_plan.steps[1].requires_approval is True

    research_plan = planner.create_plan("Research quantum computing breakthroughs")
    assert len(research_plan.steps) >= 2
    assert research_plan.steps[0].assigned_agent_id == "agent_research"


def test_planner_detects_dependency_cycle():
    agent_reg = AgentRegistry()
    tool_reg = ToolRegistry()
    planner = TaskPlanner(agent_reg, tool_reg)

    cyclic_plan = AgentPlan(
        goal="Test cycle detection",
        steps=[
            AgentStepCreate(
                step_key="step_a",
                step_order=1,
                description="Step A",
                assigned_agent_id="agent_research",
                tool_id="tool_research_fetch",
                dependencies=["step_b"],
            ),
            AgentStepCreate(
                step_key="step_b",
                step_order=2,
                description="Step B",
                assigned_agent_id="agent_research",
                tool_id="tool_research_fetch",
                dependencies=["step_a"],
            ),
        ]
    )

    with pytest.raises(TaskPlanValidationError) as exc:
        planner.validate_plan(cyclic_plan)
    assert "cyclic dependency" in str(exc.value)


def test_planner_rejects_nonexistent_dependencies():
    agent_reg = AgentRegistry()
    tool_reg = ToolRegistry()
    planner = TaskPlanner(agent_reg, tool_reg)

    invalid_plan = AgentPlan(
        goal="Missing dependency",
        steps=[
            AgentStepCreate(
                step_key="step_a",
                step_order=1,
                description="Step A",
                assigned_agent_id="agent_research",
                tool_id="tool_research_fetch",
                dependencies=["non_existent_step"],
            ),
        ]
    )
    with pytest.raises(TaskPlanValidationError) as exc:
        planner.validate_plan(invalid_plan)
    assert "depends on non-existent step" in str(exc.value)


def test_planner_rejects_unregistered_agent():
    agent_reg = AgentRegistry()
    tool_reg = ToolRegistry()
    planner = TaskPlanner(agent_reg, tool_reg)

    invalid_plan = AgentPlan(
        goal="Unknown agent",
        steps=[
            AgentStepCreate(
                step_key="step_a",
                step_order=1,
                description="Step A",
                assigned_agent_id="agent_unknown_fictional",
                tool_id="tool_research_fetch",
            ),
        ]
    )
    with pytest.raises(TaskPlanValidationError) as exc:
        planner.validate_plan(invalid_plan)
    assert "not registered" in str(exc.value)


@pytest.mark.asyncio
async def test_orchestrator_runs_multi_step_task(db_session):
    agent_reg = AgentRegistry()
    tool_reg = ToolRegistry()
    approval_mgr = ApprovalManager(tool_reg)
    events = ProgressEventPublisher()
    planner = TaskPlanner(agent_reg, tool_reg)
    orchestrator = TaskOrchestrator(agent_reg, tool_reg, approval_mgr, events)

    plan = planner.create_plan("Research modular multi-agent architectures")
    repo = AgentRepository(db_session)
    task = repo.create_task_with_plan(
        user_request="Research modular multi-agent architectures",
        title="Research Task",
        assigned_agent_id="agent_research",
        plan=plan,
    )

    # Factory returning same db_session
    class MockDbFactory:
        def __enter__(self):
            return db_session
        def __exit__(self, *args):
            pass

    await orchestrator.run_task(task_id=task.id, db_factory=MockDbFactory)

    updated_task = repo.get_task(task.id)
    assert updated_task.status == TaskStatusEnum.completed.value
    assert updated_task.progress_percent == 100
    assert updated_task.result_summary is not None
    assert all(s.status == StepStatusEnum.completed.value for s in updated_task.steps)


@pytest.mark.asyncio
async def test_consequential_action_pauses_for_approval(db_session):
    agent_reg = AgentRegistry()
    tool_reg = ToolRegistry()
    approval_mgr = ApprovalManager(tool_reg)
    events = ProgressEventPublisher()
    planner = TaskPlanner(agent_reg, tool_reg)
    orchestrator = TaskOrchestrator(agent_reg, tool_reg, approval_mgr, events)

    # Email tasks have step 2 as consequential send_email which requires approval
    plan = planner.create_plan("Draft and send email to partner@example.com")
    repo = AgentRepository(db_session)
    task = repo.create_task_with_plan(
        user_request="Draft and send email to partner@example.com",
        title="Email Task",
        assigned_agent_id="agent_email",
        plan=plan,
    )

    class MockDbFactory:
        def __enter__(self):
            return db_session
        def __exit__(self, *args):
            pass

    # First run will complete step 1 (draft) and pause on step 2 (send) awaiting approval
    await orchestrator.run_task(task_id=task.id, db_factory=MockDbFactory)

    updated_task = repo.get_task(task.id)
    assert updated_task.status == TaskStatusEnum.awaiting_approval.value
    pending_approval = repo.get_pending_approval_for_task(task.id)
    assert pending_approval is not None
    assert pending_approval.decision == "pending"
    assert "Send Email" in pending_approval.action_type

    # Verify that rejecting the approval terminates task safely
    approval_mgr.validate_and_apply_decision(
        approval=pending_approval,
        decision="rejected",
        reason="Not authorized to contact external party",
    )
    repo.update_step_status(pending_approval.step_id, StepStatusEnum.failed.value, error_message="User rejected action.")
    repo.update_task_status(task.id, TaskStatusEnum.failed.value, error_message="Consequential action rejected.")

    final_task = repo.get_task(task.id)
    assert final_task.status == TaskStatusEnum.failed.value

