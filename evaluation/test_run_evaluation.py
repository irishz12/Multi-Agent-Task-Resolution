import asyncio
import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

from run_evaluation import build_database, compute_metrics, load_scenarios, run_evaluation, run_scenario

BACKEND_DIR = EVAL_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.graph.agents import InvestigationAgent, Planner, ResolutionAgent


class FakeBedrockClient:
    def __init__(self, response: dict):
        self._response = response

    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        return json.dumps(self._response)


PLAN_RESPONSE = {
    "goal": "Resolve the customer's issue",
    "required_steps": ["identify issue", "find order", "check policy", "decide resolution"],
    "required_tools": ["customer_lookup", "order_lookup"],
}


def _planner() -> Planner:
    return Planner(bedrock_client=FakeBedrockClient(PLAN_RESPONSE))


def run(coro):
    return asyncio.run(coro)


def test_load_scenarios_from_custom_path(tmp_path):
    scenarios = [
        {
            "id": "SC-TEST-1",
            "customer_id": 1,
            "message": "hi",
            "expected_issue_type": "damaged_order",
            "expected_resolution": "REFUND",
            "expected_status": "resolved",
        }
    ]
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(scenarios))

    assert load_scenarios(path) == scenarios


def test_default_scenarios_file_has_at_least_30_entries():
    scenarios = load_scenarios()

    assert len(scenarios) >= 30

    required_keys = {"id", "customer_id", "message", "expected_issue_type", "expected_resolution", "expected_status"}
    ids = [scenario["id"] for scenario in scenarios]

    assert len(ids) == len(set(ids))
    for scenario in scenarios:
        assert required_keys.issubset(scenario.keys())


def test_compute_metrics_mixed_results():
    results = [
        {
            "predicted_issue_type": "damaged_order", "expected_issue_type": "damaged_order",
            "predicted_resolution": "REFUND", "expected_resolution": "REFUND",
            "predicted_status": "resolved", "expected_status": "resolved",
            "action_success": True, "latency_seconds": 1.0, "passed": True,
        },
        {
            "predicted_issue_type": "wrong_item", "expected_issue_type": "damaged_order",
            "predicted_resolution": "ESCALATE", "expected_resolution": "REFUND",
            "predicted_status": "escalated", "expected_status": "resolved",
            "action_success": False, "latency_seconds": 3.0, "passed": False,
        },
    ]

    metrics = compute_metrics(results)

    assert metrics["total_scenarios"] == 2
    assert metrics["total_passed"] == 1
    assert metrics["issue_classification_accuracy"] == 0.5
    assert metrics["resolution_accuracy"] == 0.5
    assert metrics["final_status_accuracy"] == 0.5
    assert metrics["action_success_rate"] == 0.5
    assert metrics["average_latency_seconds"] == 2.0


def test_compute_metrics_escalation_accuracy():
    # both predicted as escalated == expected escalated => escalation accuracy 1.0,
    # even though the second one is otherwise a mismatch (wrong issue_type).
    results = [
        {
            "predicted_issue_type": "damaged_order", "expected_issue_type": "damaged_order",
            "predicted_resolution": "ESCALATE", "expected_resolution": "ESCALATE",
            "predicted_status": "escalated", "expected_status": "escalated",
            "action_success": True, "latency_seconds": 1.0, "passed": True,
        },
        {
            "predicted_issue_type": None, "expected_issue_type": "wrong_item",
            "predicted_resolution": "ESCALATE", "expected_resolution": "ESCALATE",
            "predicted_status": "escalated", "expected_status": "escalated",
            "action_success": True, "latency_seconds": 1.0, "passed": False,
        },
    ]

    metrics = compute_metrics(results)

    assert metrics["escalation_accuracy"] == 1.0
    assert metrics["issue_classification_accuracy"] == 0.5


def test_compute_metrics_empty_results():
    metrics = compute_metrics([])

    assert metrics["total_scenarios"] == 0
    assert metrics["total_passed"] == 0
    assert metrics["average_latency_seconds"] == 0.0


def test_run_scenario_generates_expected_result_shape():
    db = build_database()
    scenario = {
        "id": "SC-TEST-2",
        "customer_id": 9001,
        "message": "My wireless earbuds arrived broken, please refund me.",
        "expected_issue_type": "damaged_order",
        "expected_resolution": "REFUND",
        "expected_status": "resolved",
    }
    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": 9101, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    result = run(run_scenario(db, scenario, planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent))

    assert result["id"] == "SC-TEST-2"
    assert result["predicted_issue_type"] == "damaged_order"
    assert result["predicted_resolution"] == "REFUND"
    assert result["predicted_status"] == "resolved"
    assert result["action_success"] is True
    assert result["passed"] is True
    assert result["latency_seconds"] >= 0


def test_run_scenario_reuses_existing_case_id():
    db = build_database()
    scenario = {
        "id": "SC-TEST-3",
        "case_id": 9501,
        "customer_id": 9007,
        "message": "Following up again about my missing package, please refund me.",
        "expected_issue_type": "missing_delivery",
        "expected_resolution": "REFUND",
        "expected_status": "resolved",
    }
    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "missing_delivery", "order_id": 9107, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "package lost"}
    ))

    result = run(run_scenario(db, scenario, planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent))

    # Case was already resolved before this scenario ran, so the duplicate
    # attempt must be blocked and the case left exactly as it was.
    assert result["case_id"] == 9501
    assert result["predicted_status"] == "resolved"
    assert result["action_success"] is False
    assert result["passed"] is True


def test_run_evaluation_writes_results_file(tmp_path):
    scenarios = [
        {
            "id": "SC-TEST-4",
            "customer_id": 9007,
            "message": "My package never arrived, please refund me.",
            "expected_issue_type": "missing_delivery",
            "expected_resolution": "REFUND",
            "expected_status": "resolved",
        }
    ]
    scenarios_path = tmp_path / "scenarios.json"
    scenarios_path.write_text(json.dumps(scenarios))
    results_path = tmp_path / "results.json"

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "missing_delivery", "order_id": 9107, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "package lost"}
    ))

    output = run(run_evaluation(
        scenarios_path, results_path,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert results_path.exists()
    saved = json.loads(results_path.read_text())

    assert saved == output
    assert saved["metrics"]["total_scenarios"] == 1
    assert saved["metrics"]["total_passed"] == 1
    assert len(saved["results"]) == 1
