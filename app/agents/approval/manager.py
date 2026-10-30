"""Approval Manager for consequential agent actions and human-in-the-loop validation."""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.schemas.agent import ApprovalDecisionEnum, ToolPermissionLevel
from app.models.agent import AgentApproval
from app.agents.tools.registry import ToolRegistry
from app.core.logging import get_logger

logger = get_logger(__name__)


class ApprovalManager:
    """Manages approval lifecycles for consequential agent actions."""

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def requires_approval(self, tool_id: Optional[str], input_data: Optional[Dict[str, Any]] = None) -> bool:
        """Determine whether a tool invocation requires explicit human approval."""
        if not tool_id:
            return False
        tool = self.tool_registry.get(tool_id)
        if not tool:
            return False
        if tool.requires_approval or tool.permission_level == ToolPermissionLevel.consequential:
            return True
        return False

    def create_approval_request(
        self,
        task_id: uuid.UUID,
        step_id: Optional[uuid.UUID],
        agent_id: str,
        action_type: str,
        description: str,
        target_resource: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        consequences_summary: Optional[str] = None,
    ) -> AgentApproval:
        """Create a pending approval record with securely bound parameters."""
        sanitized_params = dict(parameters or {})
        for k in list(sanitized_params.keys()):
            if any(s in k.lower() for s in ["password", "secret", "token", "key"]):
                sanitized_params[k] = "[REDACTED]"

        return AgentApproval(
            id=uuid.uuid4(),
            task_id=task_id,
            step_id=step_id,
            action_type=action_type,
            agent_id=agent_id,
            description=description,
            target_resource=target_resource,
            parameters=sanitized_params,
            consequences_summary=consequences_summary or f"Execution of consequential action '{action_type}'.",
            decision=ApprovalDecisionEnum.pending.value,
        )

    def validate_and_apply_decision(
        self,
        approval: AgentApproval,
        decision: ApprovalDecisionEnum,
        reason: Optional[str] = None,
        bound_action: Optional[str] = None,
        bound_target: Optional[str] = None,
    ) -> AgentApproval:
        """
        Validate decision against bound parameters to prevent authorization spoofing.
        """
        if bound_action and bound_action != approval.action_type:
            raise ValueError(f"Approval action mismatch. Expected '{approval.action_type}', got '{bound_action}'.")
        if bound_target and approval.target_resource and bound_target != approval.target_resource:
            raise ValueError(f"Approval target mismatch. Expected '{approval.target_resource}', got '{bound_target}'.")

        dec_val = decision.value if hasattr(decision, "value") else str(decision)
        approval.decision = dec_val
        approval.decision_reason = reason
        approval.decided_at = datetime.now(timezone.utc)
        return approval
