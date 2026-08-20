import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.graph.agents import InvestigationAgent, Planner, ResolutionAgent
from app.graph.graph import compiled_graph, run_case
from app.models import Case, Customer, Order, Policy


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


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def run(coro):
    return asyncio.run(coro)


def _seed_case(db, item_name, order_status, issue_type, delivered_item=None, delivery_date=None, case_status="open"):
    customer = Customer(name="Jane Doe", email="jane@example.com")
    db.add(customer)
    db.flush()

    order = Order(
        customer_id=customer.id,
        item_name=item_name,
        status=order_status,
        delivered_item=delivered_item,
        delivery_date=delivery_date,
    )
    db.add(order)
    db.flush()

    case = Case(
        customer_message="placeholder",
        customer_id=customer.id,
        order_id=order.id,
        issue_type=issue_type,
        status=case_status,
    )
    db.add(case)
    db.commit()

    return customer, order, case


def _policy(db, issue_type, refund_allowed, replacement_allowed, max_days=5):
    policy = Policy(
        issue_type=issue_type,
        refund_allowed=refund_allowed,
        replacement_allowed=replacement_allowed,
        max_resolution_days=max_days,
        description=f"{issue_type} policy",
    )
    db.add(policy)
    db.commit()
    return policy


def test_planner_creates_valid_plan(db):
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=datetime.now(timezone.utc)
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    plan = final_state["plan"]
    assert plan is not None
    assert plan.goal == PLAN_RESPONSE["goal"]
    assert plan.required_steps == PLAN_RESPONSE["required_steps"]
    assert plan.required_tools == ["customer_lookup", "order_lookup"]


def test_reflection_continues_when_evidence_complete(db):
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=datetime.now(timezone.utc)
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    reflection = final_state["reflection"]
    assert reflection.complete is True
    assert reflection.should_continue is True
    assert reflection.missing_information == []
    assert final_state["resolution"] is not None


def test_reflection_detects_missing_order_information(db):
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=datetime.now(timezone.utc)
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    # No order_id extracted: the message never mentions an order number.
    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": None, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    reflection = final_state["reflection"]
    assert reflection.complete is False
    assert reflection.should_continue is False
    assert "order_id" in reflection.missing_information


def test_missing_information_routes_to_escalation(db):
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=datetime.now(timezone.utc)
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": None, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    # Resolution agent must never even be called on this path.
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert final_state["resolution"] is None
    assert final_state["final_response"]

    db.refresh(case)
    assert case.status == "escalated"
    assert "order_id" in case.escalation_reason


def test_damaged_order_refund_flow(db):
    now = datetime.now(timezone.utc)
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=now
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert final_state["resolution"].decision == "REFUND"
    assert final_state["verification_passed"] is True
    assert final_state["action_result"]["data"]["status"] == "resolved"
    assert final_state["final_response"]

    db.refresh(case)
    assert case.status == "resolved"
    assert case.resolution == "REFUND"


def test_wrong_item_replacement_flow(db):
    now = datetime.now(timezone.utc)
    customer, order, case = _seed_case(
        db, "Blue Mug", "delivered", "wrong_item", delivered_item="Red Mug", delivery_date=now
    )
    _policy(db, "wrong_item", refund_allowed=False, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "wrong_item", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REPLACEMENT", "reason": "send correct item"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="I got a red mug instead of blue", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert final_state["resolution"].decision == "REPLACEMENT"
    assert final_state["verification_passed"] is True

    db.refresh(case)
    assert case.status == "resolved"
    assert case.resolution == "REPLACEMENT"


def test_missing_delivery_refund_flow(db):
    customer, order, case = _seed_case(db, "Gadget", "lost", "missing_delivery")
    _policy(db, "missing_delivery", refund_allowed=True, replacement_allowed=False, max_days=7)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "missing_delivery", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "package never arrived"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My package never showed up", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert final_state["resolution"].decision == "REFUND"
    assert final_state["verification_passed"] is True

    db.refresh(case)
    assert case.status == "resolved"
    assert case.resolution == "REFUND"


def test_resolution_agent_escalates(db):
    now = datetime.now(timezone.utc)
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=now
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "ESCALATE", "reason": "evidence is unclear"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert final_state["resolution"].decision == "ESCALATE"
    assert final_state["verification_passed"] is None
    assert final_state["final_response"]

    db.refresh(case)
    assert case.status == "escalated"
    assert case.escalation_reason == "evidence is unclear"


def test_resolution_action_failure_escalates(db):
    # Case was already closed by a prior request (race condition) — resolution_action
    # must fail at the tool layer even though ResolutionAgent proposes an allowed action.
    now = datetime.now(timezone.utc)
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=now,
        case_status="resolved",
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert final_state["verification_passed"] is False
    assert final_state["action_result"]["success"] is False
    assert final_state["final_response"]

    db.refresh(case)
    assert case.status == "resolved"


def test_graph_reaches_end_with_final_response(db):
    now = datetime.now(timezone.utc)
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=now
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert set(final_state.keys()) == {
        "case_id", "customer_message", "customer_id", "plan", "investigation", "reflection",
        "resolution", "action_result", "verification_passed", "final_response",
    }
    assert isinstance(final_state["final_response"], str)
    assert final_state["final_response"] != ""


def test_compiled_graph_ainvoke_is_actually_used(db):
    now = datetime.now(timezone.utc)
    customer, order, case = _seed_case(
        db, "Widget", "delivered_damaged", "damaged_order", delivered_item="Widget", delivery_date=now
    )
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    with patch.object(compiled_graph, "ainvoke", wraps=compiled_graph.ainvoke) as spy:
        final_state = run(run_case(
            db, case_id=case.id, customer_message="My item arrived broken", customer_id=customer.id,
            planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
        ))

    spy.assert_called_once()
    assert final_state["resolution"].decision == "REFUND"


def test_run_case_with_invalid_customer_id_escalates_safely(db):
    # No Customer row exists for this id — run_case() is called directly here,
    # bypassing the API route's own pre-check (routes/cases.py validates the
    # customer before ever calling run_case). The graph must still degrade
    # safely rather than crash or silently proceed.
    now = datetime.now(timezone.utc)
    order = Order(customer_id=9999, item_name="Widget", status="delivered_damaged", delivered_item="Widget", delivery_date=now)
    db.add(order)
    db.flush()
    case = Case(customer_message="My item arrived broken", customer_id=9999, issue_type="damaged_order", status="open")
    db.add(case)
    db.commit()
    _policy(db, "damaged_order", refund_allowed=True, replacement_allowed=True)

    investigation_agent = InvestigationAgent(bedrock_client=FakeBedrockClient(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]}
    ))
    resolution_agent = ResolutionAgent(bedrock_client=FakeBedrockClient(
        {"decision": "REFUND", "reason": "confirmed damaged"}
    ))

    final_state = run(run_case(
        db, case_id=case.id, customer_message="My item arrived broken", customer_id=9999,
        planner=_planner(), investigation_agent=investigation_agent, resolution_agent=resolution_agent,
    ))

    assert "customer not found" in final_state["investigation"].missing_information
    assert final_state["reflection"].complete is False
    assert final_state["resolution"] is None

    db.refresh(case)
    assert case.status == "escalated"
