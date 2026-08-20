from pydantic import BaseModel

from app.graph.state import CaseState


class InvestigationPlanOut(BaseModel):
    goal: str
    required_steps: list[str]
    required_tools: list[str]


class ReflectionOut(BaseModel):
    complete: bool
    missing_information: list[str]
    should_continue: bool


class WorkflowStepOut(BaseModel):
    key: str
    agent: str
    status: str
    description: str
    tools: list[str]


def build_workflow_summary(state: CaseState, final_status: str) -> tuple[list[WorkflowStepOut], list[str]]:
    """Build the API-facing step list and tools-used list straight from the
    graph's real final state — no text inference, no heuristics."""
    steps: list[WorkflowStepOut] = []
    tools_used: list[str] = []

    plan = state.get("plan")
    steps.append(WorkflowStepOut(
        key="planner",
        agent="Planner Agent",
        status="success",
        description=plan.goal if plan else "Created an investigation plan.",
        tools=[],
    ))

    investigation = state.get("investigation")
    investigation_tools: list[str] = []
    if investigation:
        if "customer" in investigation.evidence:
            investigation_tools.append("customer_lookup")
        if "order" in investigation.evidence:
            investigation_tools.append("order_lookup")
    tools_used.extend(investigation_tools)
    steps.append(WorkflowStepOut(
        key="investigation",
        agent="Investigation Agent",
        status="success",
        description=(
            f'Classified the issue as "{investigation.issue_type}" and gathered evidence.'
            if investigation and investigation.issue_type
            else "Attempted to classify the issue and gather evidence."
        ),
        tools=investigation_tools,
    ))

    reflection = state.get("reflection")
    reflection_complete = bool(reflection and reflection.complete)
    steps.append(WorkflowStepOut(
        key="reflection",
        agent="Reflection",
        status="success" if reflection_complete else "warning",
        description=(
            "Evidence was complete; continuing to the Resolution Agent."
            if reflection_complete
            else f"Evidence incomplete: {', '.join(reflection.missing_information)}"
            if reflection
            else "Reflection did not run."
        ),
        tools=[],
    ))

    resolution = state.get("resolution")
    if resolution is None:
        steps.append(WorkflowStepOut(
            key="resolution", agent="Resolution Agent", status="skipped",
            description="Skipped — investigation evidence was incomplete.", tools=[],
        ))
    else:
        resolution_tools = ["policy_lookup"] if resolution.policy else []
        tools_used.extend(resolution_tools)
        steps.append(WorkflowStepOut(
            key="resolution",
            agent="Resolution Agent",
            status="success" if resolution.decision in ("REFUND", "REPLACEMENT") else "warning",
            description=resolution.reason,
            tools=resolution_tools,
        ))

    action_result = state.get("action_result")
    verification_passed = state.get("verification_passed")

    if resolution is None or resolution.decision == "ESCALATE":
        steps.append(WorkflowStepOut(
            key="action", agent="Action Execution", status="skipped",
            description="Skipped — no resolution was executed.", tools=[],
        ))
        steps.append(WorkflowStepOut(
            key="verification", agent="Verification", status="skipped",
            description="Skipped — no action was executed.", tools=[],
        ))
    else:
        action_success = bool(action_result and action_result.get("success"))
        if action_result:
            tools_used.append("resolution_action")
        steps.append(WorkflowStepOut(
            key="action",
            agent="Action Execution",
            status="success" if action_success else "warning",
            description=(
                f"Executed {resolution.decision.lower()} and recorded an action reference."
                if action_success
                else (action_result or {}).get("error") or "The action failed to execute."
            ),
            tools=["resolution_action"] if action_result else [],
        ))
        steps.append(WorkflowStepOut(
            key="verification",
            agent="Verification",
            status="success" if verification_passed else "warning",
            description=(
                "Confirmed the action succeeded before responding."
                if verification_passed
                else "Verification failed; the case was routed to escalation."
            ),
            tools=[],
        ))

    if final_status == "escalated":
        tools_used.append("escalate_case")

    return steps, sorted(set(tools_used))
