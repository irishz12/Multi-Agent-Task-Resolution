from app.graph.agents import InvestigationPlan, InvestigationResult, ReflectionResult, ResolutionResult
from app.routes.workflow_summary import build_workflow_summary


def _base_state(**overrides):
    state = {
        "plan": InvestigationPlan(goal="Resolve the customer's issue", required_steps=["identify issue"], required_tools=["order_lookup"]),
        "investigation": None,
        "reflection": None,
        "resolution": None,
        "action_result": None,
        "verification_passed": None,
    }
    state.update(overrides)
    return state


def test_resolved_case_has_all_success_steps_and_expected_tools():
    state = _base_state(
        investigation=InvestigationResult(
            issue_type="damaged_order", customer_id=1, order_id=1,
            evidence={"customer": {"id": 1}, "order": {"id": 1}},
            missing_information=[], investigation_complete=True,
        ),
        reflection=ReflectionResult(complete=True, missing_information=[], should_continue=True),
        resolution=ResolutionResult(decision="REFUND", reason="confirmed damaged", policy={"issue_type": "damaged_order"}, ready_for_action=True),
        action_result={"success": True, "data": {"resolution": "REFUND", "action_reference": "ACT-1"}},
        verification_passed=True,
    )

    steps, tools_used = build_workflow_summary(state, final_status="resolved")

    assert [s.key for s in steps] == ["planner", "investigation", "reflection", "resolution", "action", "verification"]
    assert all(s.status == "success" for s in steps)
    assert tools_used == ["customer_lookup", "order_lookup", "policy_lookup", "resolution_action"]


def test_incomplete_investigation_skips_downstream_steps():
    state = _base_state(
        investigation=InvestigationResult(
            issue_type="damaged_order", customer_id=1, order_id=None,
            evidence={}, missing_information=["order_id"], investigation_complete=False,
        ),
        reflection=ReflectionResult(complete=False, missing_information=["order_id"], should_continue=False),
    )

    steps, tools_used = build_workflow_summary(state, final_status="escalated")

    by_key = {s.key: s for s in steps}
    assert by_key["reflection"].status == "warning"
    assert by_key["resolution"].status == "skipped"
    assert by_key["action"].status == "skipped"
    assert by_key["verification"].status == "skipped"
    assert "escalate_case" in tools_used


def test_resolution_agent_escalation_skips_action_and_verification():
    state = _base_state(
        investigation=InvestigationResult(
            issue_type="wrong_item", customer_id=1, order_id=1,
            evidence={"customer": {"id": 1}, "order": {"id": 1}},
            missing_information=[], investigation_complete=True,
        ),
        reflection=ReflectionResult(complete=True, missing_information=[], should_continue=True),
        resolution=ResolutionResult(decision="ESCALATE", reason="refund not allowed by policy", policy={"issue_type": "wrong_item"}, ready_for_action=False),
    )

    steps, tools_used = build_workflow_summary(state, final_status="escalated")

    by_key = {s.key: s for s in steps}
    assert by_key["resolution"].status == "warning"
    assert by_key["action"].status == "skipped"
    assert by_key["verification"].status == "skipped"
    assert "policy_lookup" in tools_used
    assert "escalate_case" in tools_used
    assert "resolution_action" not in tools_used


def test_action_execution_failure_marks_action_and_verification_as_warning():
    state = _base_state(
        investigation=InvestigationResult(
            issue_type="damaged_order", customer_id=1, order_id=1,
            evidence={"customer": {"id": 1}, "order": {"id": 1}},
            missing_information=[], investigation_complete=True,
        ),
        reflection=ReflectionResult(complete=True, missing_information=[], should_continue=True),
        resolution=ResolutionResult(decision="REFUND", reason="confirmed damaged", policy={"issue_type": "damaged_order"}, ready_for_action=True),
        action_result={"success": False, "error": "case is already resolved"},
        verification_passed=False,
    )

    steps, tools_used = build_workflow_summary(state, final_status="escalated")

    by_key = {s.key: s for s in steps}
    assert by_key["action"].status == "warning"
    assert by_key["action"].description == "case is already resolved"
    assert by_key["verification"].status == "warning"
    assert "escalate_case" in tools_used
