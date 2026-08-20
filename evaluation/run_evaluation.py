"""Evaluation harness for the AgentFlow Support LangGraph workflow.

Runs every scenario in scenarios.json through the real compiled LangGraph
(run_case), against a fresh self-contained SQLite database seeded with fixed
fixture data, and reports how closely the system's actual behavior matches
the expected outcome for each scenario.

Run from the backend/ directory so backend/.env is picked up:

    cd backend
    .venv/bin/python ../evaluation/run_evaluation.py
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.graph.graph import run_case
from app.models import Case, Customer, Order, Policy

SCENARIOS_PATH = EVAL_DIR / "scenarios.json"
RESULTS_PATH = EVAL_DIR / "results.json"

PRESEEDED_RESOLVED_CASE_ID = 9501


def build_database():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _seed_fixtures(session)
    return session


def _seed_fixtures(db):
    now = datetime.now(timezone.utc)
    recent = lambda days: now - timedelta(days=days)
    stale = now - timedelta(days=30)

    customers = [
        Customer(id=9001, name="Alice Nguyen", email="alice.nguyen@example.com"),
        Customer(id=9002, name="Ben Carter", email="ben.carter@example.com"),
        Customer(id=9003, name="Chloe Davis", email="chloe.davis@example.com"),
        Customer(id=9004, name="Daniel Kim", email="daniel.kim@example.com"),
        Customer(id=9005, name="Ella Rossi", email="ella.rossi@example.com"),
        Customer(id=9006, name="Felix Brown", email="felix.brown@example.com"),
        Customer(id=9007, name="Grace Lee", email="grace.lee@example.com"),
        Customer(id=9008, name="Henry Wolf", email="henry.wolf@example.com"),
        Customer(id=9009, name="Ivy Chen", email="ivy.chen@example.com"),
        Customer(id=9010, name="Jack Turner", email="jack.turner@example.com"),
    ]
    db.add_all(customers)
    db.flush()

    orders = [
        Order(id=9101, customer_id=9001, item_name="Wireless Earbuds", status="delivered_damaged", delivered_item="Wireless Earbuds", delivery_date=recent(2)),
        Order(id=9102, customer_id=9002, item_name="Blender", status="delivered_damaged", delivered_item="Blender", delivery_date=recent(1)),
        Order(id=9103, customer_id=9003, item_name="Ceramic Vase", status="delivered_damaged", delivered_item="Ceramic Vase", delivery_date=stale),
        Order(id=9104, customer_id=9004, item_name="Laptop Stand", status="delivered", delivered_item="Phone Stand", delivery_date=recent(2)),
        Order(id=9105, customer_id=9005, item_name="Sneakers", status="delivered", delivered_item="Sandals", delivery_date=recent(1)),
        Order(id=9106, customer_id=9006, item_name="Monitor", status="delivered", delivered_item="Keyboard", delivery_date=stale),
        Order(id=9107, customer_id=9007, item_name="Bookshelf", status="lost", delivered_item=None, delivery_date=None),
        Order(id=9108, customer_id=9008, item_name="Desk Fan", status="lost", delivered_item=None, delivery_date=None),
        Order(id=9109, customer_id=9009, item_name="Water Bottle", status="delivered", delivered_item="Water Bottle", delivery_date=recent(3)),
        Order(id=9110, customer_id=9010, item_name="Table Lamp", status="delivered_damaged", delivered_item="Table Lamp", delivery_date=recent(2)),
    ]
    db.add_all(orders)

    policies = [
        Policy(issue_type="damaged_order", refund_allowed=True, replacement_allowed=True, max_resolution_days=5, description="Damaged order policy"),
        Policy(issue_type="missing_delivery", refund_allowed=True, replacement_allowed=False, max_resolution_days=7, description="Missing delivery policy"),
        Policy(issue_type="wrong_item", refund_allowed=False, replacement_allowed=True, max_resolution_days=5, description="Wrong item policy"),
    ]
    db.add_all(policies)

    # Used by the "already resolved case" scenario, to prove a closed case is left alone.
    db.add(Case(
        id=PRESEEDED_RESOLVED_CASE_ID,
        customer_message="My package never arrived, please refund me.",
        customer_id=9007,
        issue_type="missing_delivery",
        resolution="REFUND",
        status="resolved",
        action_reference="ACT-PRESEEDED01",
    ))

    db.commit()


def load_scenarios(path=SCENARIOS_PATH):
    with open(path) as f:
        return json.load(f)


async def run_scenario(db, scenario, planner=None, investigation_agent=None, resolution_agent=None):
    case_id = scenario.get("case_id")
    if case_id is None:
        case = Case(customer_message=scenario["message"], customer_id=scenario["customer_id"], status="processing")
        db.add(case)
        db.commit()
        db.refresh(case)
        case_id = case.id

    start = time.monotonic()
    final_state = await run_case(
        db,
        case_id=case_id,
        customer_message=scenario["message"],
        customer_id=scenario["customer_id"],
        planner=planner,
        investigation_agent=investigation_agent,
        resolution_agent=resolution_agent,
    )
    latency = time.monotonic() - start

    case = db.get(Case, case_id)
    action_result = final_state.get("action_result") or {}

    return {
        "id": scenario["id"],
        "case_id": case_id,
        "predicted_issue_type": case.issue_type,
        "predicted_resolution": case.resolution,
        "predicted_status": case.status,
        "action_success": bool(action_result.get("success")),
        "latency_seconds": round(latency, 3),
        "expected_issue_type": scenario["expected_issue_type"],
        "expected_resolution": scenario["expected_resolution"],
        "expected_status": scenario["expected_status"],
        "passed": (
            case.issue_type == scenario["expected_issue_type"]
            and case.resolution == scenario["expected_resolution"]
            and case.status == scenario["expected_status"]
        ),
    }


def compute_metrics(results):
    total = len(results)
    if total == 0:
        return {
            "total_scenarios": 0,
            "total_passed": 0,
            "issue_classification_accuracy": 0.0,
            "resolution_accuracy": 0.0,
            "final_status_accuracy": 0.0,
            "escalation_accuracy": 0.0,
            "action_success_rate": 0.0,
            "average_latency_seconds": 0.0,
        }

    def rate(predicate):
        return sum(1 for r in results if predicate(r)) / total

    return {
        "total_scenarios": total,
        "total_passed": sum(1 for r in results if r["passed"]),
        "issue_classification_accuracy": round(rate(lambda r: r["predicted_issue_type"] == r["expected_issue_type"]), 4),
        "resolution_accuracy": round(rate(lambda r: r["predicted_resolution"] == r["expected_resolution"]), 4),
        "final_status_accuracy": round(rate(lambda r: r["predicted_status"] == r["expected_status"]), 4),
        "escalation_accuracy": round(
            rate(lambda r: (r["predicted_status"] == "escalated") == (r["expected_status"] == "escalated")), 4
        ),
        "action_success_rate": round(rate(lambda r: r["action_success"]), 4),
        "average_latency_seconds": round(sum(r["latency_seconds"] for r in results) / total, 3),
    }


async def run_evaluation(scenarios_path=SCENARIOS_PATH, results_path=RESULTS_PATH, planner=None, investigation_agent=None, resolution_agent=None):
    scenarios = load_scenarios(scenarios_path)
    db = build_database()

    results = []
    for scenario in scenarios:
        result = await run_scenario(db, scenario, planner=planner, investigation_agent=investigation_agent, resolution_agent=resolution_agent)
        results.append(result)
        print(
            f"{result['id']}: {'PASS' if result['passed'] else 'FAIL'} "
            f"(issue={result['predicted_issue_type']}, resolution={result['predicted_resolution']}, "
            f"status={result['predicted_status']}, {result['latency_seconds']}s)"
        )

    output = {"metrics": compute_metrics(results), "results": results}

    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)

    return output


def main():
    parser = argparse.ArgumentParser(description="Run the AgentFlow Support evaluation suite.")
    parser.add_argument("--scenarios", default=str(SCENARIOS_PATH), help="Path to scenarios.json")
    parser.add_argument("--output", default=str(RESULTS_PATH), help="Path to write results.json")
    args = parser.parse_args()

    output = asyncio.run(run_evaluation(Path(args.scenarios), Path(args.output)))

    print("\n--- Summary ---")
    for key, value in output["metrics"].items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
