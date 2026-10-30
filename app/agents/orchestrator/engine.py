"""Task Orchestrator coordinating plan execution, concurrency, retries, approvals, and events."""
import asyncio
import uuid
from typing import Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from app.agents.base import AgentStepContext
from app.agents.registry import AgentRegistry
from app.agents.tools.registry import ToolRegistry
from app.agents.approval.manager import ApprovalManager
from app.agents.events.publisher import ProgressEventPublisher
from app.ai.base import BaseAIProvider
from app.core.logging import get_logger
from app.models.agent import AgentTask, AgentTaskStep
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import TaskStatusEnum, StepStatusEnum, ApprovalDecisionEnum

logger = get_logger(__name__)


class TaskOrchestrator:
    """Coordinates execution of multi-step agent plans with lifecycle enforcement."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        tool_registry: ToolRegistry,
        approval_manager: ApprovalManager,
        event_publisher: ProgressEventPublisher,
    ):
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry
        self.approval_manager = approval_manager
        self.event_publisher = event_publisher
        self._cancelled_tasks: Set[uuid.UUID] = set()
        self._running_tasks: Dict[uuid.UUID, asyncio.Task] = {}

    def cancel_task(self, task_id: uuid.UUID) -> None:
        """Signal cancellation for a running task."""
        self._cancelled_tasks.add(task_id)
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()

    async def run_task(
        self,
        task_id: uuid.UUID,
        db_factory: Any,
        ai_provider: Optional[BaseAIProvider] = None,
        desktop_service: Optional[Any] = None,
    ) -> None:
        """Execute a task through its plan steps until completion or approval pause."""
        logger.info("TaskOrchestrator beginning execution for task: %s", task_id)

        # 1. Update task to running state
        with db_factory() as db:
            repo = AgentRepository(db)
            task = repo.update_task_status(task_id, TaskStatusEnum.running.value)
            if not task:
                return
            repo.add_execution_log(task_id, "agent.task.started", f"Task '{task.title}' initiated.")
            await self.event_publisher.publish(
                "agent.task.started",
                task_id,
                {"status": TaskStatusEnum.running.value, "title": task.title}
            )

        step_results: Dict[str, Any] = {}

        # Main execution loop
        while True:
            if task_id in self._cancelled_tasks:
                with db_factory() as db:
                    repo = AgentRepository(db)
                    repo.update_task_status(task_id, TaskStatusEnum.cancelled.value, error_message="Task was cancelled by user.")
                    repo.add_execution_log(task_id, "agent.task.cancelled", "Task cancelled.")
                    await self.event_publisher.publish("agent.task.cancelled", task_id, {"status": "cancelled"})
                break

            with db_factory() as db:
                repo = AgentRepository(db)
                task = repo.get_task(task_id)
                if not task:
                    break

                # Check if task is already in terminal state
                if task.status in (TaskStatusEnum.completed.value, TaskStatusEnum.failed.value, TaskStatusEnum.cancelled.value):
                    break

                steps = list(task.steps)
                total_steps = len(steps)
                completed_count = sum(1 for s in steps if s.status == StepStatusEnum.completed.value)
                progress = int((completed_count / total_steps) * 100) if total_steps > 0 else 0
                repo.update_task_status(task_id, task.status, progress_percent=progress)

                # Determine step states
                step_map = {s.step_key: s for s in steps}
                ready_steps = []

                all_done = True
                has_failed = False

                for s in steps:
                    if s.status == StepStatusEnum.failed.value:
                        has_failed = True
                    elif s.status == StepStatusEnum.pending.value:
                        all_done = False
                        # Check dependencies
                        deps_satisfied = True
                        for dep in (s.dependencies or []):
                            dep_step = step_map.get(dep)
                            if not dep_step or dep_step.status != StepStatusEnum.completed.value:
                                deps_satisfied = False
                                if dep_step and dep_step.status in (StepStatusEnum.failed.value, StepStatusEnum.skipped.value, StepStatusEnum.cancelled.value):
                                    # Prerequisite failed or skipped; skip this step
                                    repo.update_step_status(s.id, StepStatusEnum.skipped.value, error_message=f"Prerequisite '{dep}' was not successful.")
                                break
                        if deps_satisfied:
                            ready_steps.append(s)
                    elif s.status == StepStatusEnum.running.value:
                        all_done = False
                    elif s.status == StepStatusEnum.awaiting_approval.value:
                        all_done = False

                if all_done:
                    final_status = TaskStatusEnum.failed.value if has_failed else TaskStatusEnum.completed.value
                    summary = self._consolidate_summary(steps, has_failed)
                    repo.update_task_status(task_id, final_status, progress_percent=100, result_summary=summary)
                    repo.add_execution_log(task_id, f"agent.task.{final_status}", summary)
                    await self.event_publisher.publish(
                        f"agent.task.{final_status}",
                        task_id,
                        {"status": final_status, "result_summary": summary}
                    )
                    break

                if not ready_steps:
                    # Check if waiting for an approval
                    pending_approval = repo.get_pending_approval_for_task(task_id)
                    if pending_approval:
                        # Paused for human approval
                        break
                    # If nothing is ready and not all done, but some are running/failed
                    if has_failed and not any(s.status in (StepStatusEnum.pending.value, StepStatusEnum.running.value) for s in steps):
                        summary = "Task halted due to failed step prerequisites."
                        repo.update_task_status(task_id, TaskStatusEnum.failed.value, error_message=summary)
                        await self.event_publisher.publish("agent.task.failed", task_id, {"status": "failed", "error": summary})
                        break
                    await asyncio.sleep(0.5)
                    continue

                # Process ready steps
                # Check for consequential approval requirement before execution
                approval_needed_step = None
                for s in ready_steps:
                    if s.requires_approval:
                        approval_needed_step = s
                        break

                if approval_needed_step:
                    # Pause task and request approval
                    step = approval_needed_step
                    tool = self.tool_registry.get(step.tool_id) if step.tool_id else None
                    action_type = tool.name if tool else "Consequential Agent Action"
                    approval = self.approval_manager.create_approval_request(
                        task_id=task_id,
                        step_id=step.id,
                        agent_id=step.assigned_agent_id,
                        action_type=action_type,
                        description=step.description,
                        target_resource=step.tool_id,
                        parameters=step.input_data,
                        consequences_summary=f"Requires human authorization to execute tool '{step.tool_id}'."
                    )
                    repo.create_approval(approval)
                    repo.update_step_status(step.id, StepStatusEnum.awaiting_approval.value)
                    repo.update_task_status(task_id, TaskStatusEnum.awaiting_approval.value)
                    repo.add_execution_log(
                        task_id,
                        "agent.approval.required",
                        f"Step '{step.step_key}' requires approval: {action_type}",
                        step_key=step.step_key
                    )
                    await self.event_publisher.publish(
                        "agent.approval.required",
                        task_id,
                        {
                            "approval_id": str(approval.id),
                            "step_key": step.step_key,
                            "action_type": action_type,
                            "description": step.description,
                        },
                        step_key=step.step_key
                    )
                    # Pause task until approved
                    break

            # Execute safe ready steps concurrently (bounded to max 3)
            concurrency_limit = 3
            batch = ready_steps[:concurrency_limit]
            tasks = [
                self._execute_single_step(
                    task_id=task_id,
                    step_id=s.id,
                    step_key=s.step_key,
                    agent_id=s.assigned_agent_id,
                    description=s.description,
                    tool_id=s.tool_id,
                    input_data=s.input_data or {},
                    prior_results=step_results,
                    db_factory=db_factory,
                    ai_provider=ai_provider,
                    desktop_service=desktop_service,
                )
                for s in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for s, res in zip(batch, batch_results):
                if isinstance(res, dict):
                    step_results[s.step_key] = res

    async def _execute_single_step(
        self,
        task_id: uuid.UUID,
        step_id: uuid.UUID,
        step_key: str,
        agent_id: str,
        description: str,
        tool_id: Optional[str],
        input_data: Dict[str, Any],
        prior_results: Dict[str, Any],
        db_factory: Any,
        ai_provider: Optional[BaseAIProvider],
        desktop_service: Optional[Any],
    ) -> Dict[str, Any]:
        """Execute one step with bounded retries and logging."""
        with db_factory() as db:
            repo = AgentRepository(db)
            repo.update_step_status(step_id, StepStatusEnum.running.value)
            repo.add_execution_log(task_id, "agent.step.started", f"Starting step '{step_key}': {description}", step_key=step_key)
            await self.event_publisher.publish("agent.step.started", task_id, {"step_key": step_key, "description": description}, step_key=step_key)

        agent = self.agent_registry.get(agent_id)
        if not agent or not agent.enabled:
            err = f"Assigned agent '{agent_id}' is unavailable."
            with db_factory() as db:
                repo = AgentRepository(db)
                repo.update_step_status(step_id, StepStatusEnum.failed.value, error_message=err)
                repo.add_execution_log(task_id, "agent.step.failed", err, step_key=step_key)
                await self.event_publisher.publish("agent.step.failed", task_id, {"step_key": step_key, "error": err}, step_key=step_key)
            return {"error": err}

        context = AgentStepContext(
            task_id=str(task_id),
            step_key=step_key,
            description=description,
            input_data=input_data,
            tool_id=tool_id,
            task_user_request=description,
            prior_step_results=prior_results,
        )

        attempts = 0
        max_attempts = agent.max_retries + 1
        last_error = None

        while attempts < max_attempts:
            attempts += 1
            try:
                with db_factory() as db:
                    result = await agent.execute_step(
                        context=context,
                        tool_registry=self.tool_registry,
                        ai_provider=ai_provider,
                        db_session=db,
                        desktop_service=desktop_service,
                    )
                # Success
                with db_factory() as db:
                    repo = AgentRepository(db)
                    repo.update_step_status(step_id, StepStatusEnum.completed.value, output_data=result)
                    repo.add_execution_log(task_id, "agent.step.completed", f"Step '{step_key}' completed.", step_key=step_key)
                    await self.event_publisher.publish("agent.step.completed", task_id, {"step_key": step_key, "result": result}, step_key=step_key)
                return result

            except Exception as e:
                last_error = str(e)
                logger.warning("Step '%s' attempt %d failed: %s", step_key, attempts, last_error)
                with db_factory() as db:
                    repo = AgentRepository(db)
                    repo.update_step_status(step_id, StepStatusEnum.running.value, increment_retry=True)
                if attempts < max_attempts:
                    await asyncio.sleep(0.5 * attempts)

        # Retry exhaustion
        err_msg = f"Step '{step_key}' failed after {attempts} attempts. Error: {last_error}"
        with db_factory() as db:
            repo = AgentRepository(db)
            repo.update_step_status(step_id, StepStatusEnum.failed.value, error_message=err_msg)
            repo.add_execution_log(task_id, "agent.step.failed", err_msg, step_key=step_key)
            await self.event_publisher.publish("agent.step.failed", task_id, {"step_key": step_key, "error": err_msg}, step_key=step_key)
        return {"error": err_msg}

    def _consolidate_summary(self, steps: list, has_failed: bool) -> str:
        completed = [s for s in steps if s.status == StepStatusEnum.completed.value]
        failed = [s for s in steps if s.status == StepStatusEnum.failed.value]

        if not has_failed:
            summaries = []
            for s in completed:
                if s.output_data and "summary" in s.output_data:
                    summaries.append(s.output_data["summary"])
                else:
                    summaries.append(f"{s.description}: Done.")
            return "Task completed successfully.\n" + "\n".join(f"- {s}" for s in summaries)
        else:
            return f"Task completed with partial failures. {len(completed)} step(s) succeeded; {len(failed)} step(s) encountered errors."

