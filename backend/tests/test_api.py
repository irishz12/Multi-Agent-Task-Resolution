import json
import logging
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.bedrock_client import BedrockClientError
from app.db import Base, get_db
from app.graph.agents import InvestigationAgent, Planner, ResolutionAgent
from app.main import app
from app.models import Case, Customer, Order, Policy
from app.routes.cases import get_investigation_agent, get_planner, get_resolution_agent

PLAN_RESPONSE = {
    "goal": "Resolve the customer's issue",
    "required_steps": ["identify issue", "find order", "check policy", "decide resolution"],
    "required_tools": ["customer_lookup", "order_lookup"],
}


class FakeBedrockClient:
    def __init__(self, response: dict):
        self._response = response

    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        return json.dumps(self._response)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _override_agents(investigation_response: dict, resolution_response: dict):
    app.dependency_overrides[get_planner] = lambda: Planner(bedrock_client=FakeBedrockClient(PLAN_RESPONSE))
    app.dependency_overrides[get_investigation_agent] = lambda: InvestigationAgent(
        bedrock_client=FakeBedrockClient(investigation_response)
    )
    app.dependency_overrides[get_resolution_agent] = lambda: ResolutionAgent(
        bedrock_client=FakeBedrockClient(resolution_response)
    )


def _seed_customer_and_order(db_session, item_name, order_status, delivered_item=None, delivery_date=None):
    customer = Customer(name="Jane Doe", email="jane@example.com")
    db_session.add(customer)
    db_session.flush()

    order = Order(
        customer_id=customer.id,
        item_name=item_name,
        status=order_status,
        delivered_item=delivered_item,
        delivery_date=delivery_date,
    )
    db_session.add(order)
    db_session.commit()

    return customer, order


def _seed_policy(db_session, issue_type, refund_allowed, replacement_allowed, max_days=5):
    policy = Policy(
        issue_type=issue_type,
        refund_allowed=refund_allowed,
        replacement_allowed=replacement_allowed,
        max_resolution_days=max_days,
        description=f"{issue_type} policy",
    )
    db_session.add(policy)
    db_session.commit()


def test_damaged_order_flow_success(client, db_session):
    now = datetime.now(timezone.utc)
    customer, order = _seed_customer_and_order(db_session, "Widget", "delivered_damaged", delivered_item="Widget", delivery_date=now)
    _seed_policy(db_session, "damaged_order", refund_allowed=True, replacement_allowed=True)
    _override_agents(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]},
        {"decision": "REFUND", "reason": "confirmed damaged"},
    )

    response = client.post("/api/cases/resolve", json={"customer_id": customer.id, "message": "My item arrived broken"})

    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "damaged_order"
    assert body["resolution"] == "REFUND"
    assert body["status"] == "resolved"
    assert body["action_reference"] is not None
    assert body["message"]

    assert body["plan"]["goal"]
    assert body["reflection"] == {"complete": True, "missing_information": [], "should_continue": True}
    assert [step["key"] for step in body["steps"]] == ["planner", "investigation", "reflection", "resolution", "action", "verification"]
    assert all(step["status"] == "success" for step in body["steps"])
    assert "customer_lookup" in body["tools_used"]
    assert "order_lookup" in body["tools_used"]
    assert "policy_lookup" in body["tools_used"]
    assert "resolution_action" in body["tools_used"]
    assert body["resolution_reason"] == "confirmed damaged"


def test_wrong_item_replacement_flow(client, db_session):
    now = datetime.now(timezone.utc)
    customer, order = _seed_customer_and_order(db_session, "Blue Mug", "delivered", delivered_item="Red Mug", delivery_date=now)
    _seed_policy(db_session, "wrong_item", refund_allowed=False, replacement_allowed=True)
    _override_agents(
        {"issue_type": "wrong_item", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]},
        {"decision": "REPLACEMENT", "reason": "send correct item"},
    )

    response = client.post("/api/cases/resolve", json={"customer_id": customer.id, "message": "I got a red mug instead of blue"})

    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "wrong_item"
    assert body["resolution"] == "REPLACEMENT"
    assert body["status"] == "resolved"
    assert body["action_reference"] is not None


def test_escalation_flow(client, db_session):
    now = datetime.now(timezone.utc)
    customer, order = _seed_customer_and_order(db_session, "Widget", "delivered_damaged", delivered_item="Widget", delivery_date=now)
    _seed_policy(db_session, "damaged_order", refund_allowed=True, replacement_allowed=True)
    _override_agents(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]},
        {"decision": "ESCALATE", "reason": "evidence is unclear"},
    )

    response = client.post("/api/cases/resolve", json={"customer_id": customer.id, "message": "My item arrived broken"})

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "ESCALATE"
    assert body["status"] == "escalated"
    assert body["action_reference"] is None
    assert body["message"]

    by_key = {step["key"]: step for step in body["steps"]}
    assert by_key["resolution"]["status"] == "warning"
    assert by_key["action"]["status"] == "skipped"
    assert by_key["verification"]["status"] == "skipped"
    assert "escalate_case" in body["tools_used"]
    assert body["resolution_reason"] == "evidence is unclear"


def test_get_case_returns_saved_details(client, db_session):
    now = datetime.now(timezone.utc)
    customer, order = _seed_customer_and_order(db_session, "Widget", "delivered_damaged", delivered_item="Widget", delivery_date=now)
    _seed_policy(db_session, "damaged_order", refund_allowed=True, replacement_allowed=True)
    _override_agents(
        {"issue_type": "damaged_order", "order_id": order.id, "requested_tools": ["customer_lookup", "order_lookup"]},
        {"decision": "REFUND", "reason": "confirmed damaged"},
    )

    created = client.post("/api/cases/resolve", json={"customer_id": customer.id, "message": "My item arrived broken"})
    case_id = created.json()["case_id"]

    response = client.get(f"/api/cases/{case_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == case_id
    assert body["issue_type"] == "damaged_order"
    assert body["resolution"] == "REFUND"
    assert body["status"] == "resolved"
    assert body["customer_message"] == "My item arrived broken"


def test_invalid_customer_returns_404(client, db_session):
    response = client.post("/api/cases/resolve", json={"customer_id": 9999, "message": "My item arrived broken"})

    assert response.status_code == 404
    assert db_session.query(Case).count() == 0


def test_bedrock_failure_escalates_case_instead_of_hanging_in_processing(client, db_session, caplog):
    now = datetime.now(timezone.utc)
    customer, order = _seed_customer_and_order(db_session, "Widget", "delivered_damaged", delivered_item="Widget", delivery_date=now)
    _seed_policy(db_session, "damaged_order", refund_allowed=True, replacement_allowed=True)

    class FailingBedrockClient:
        async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
            raise BedrockClientError("Bedrock request failed: connection error")

    app.dependency_overrides[get_planner] = lambda: Planner(bedrock_client=FailingBedrockClient())
    app.dependency_overrides[get_investigation_agent] = lambda: InvestigationAgent(bedrock_client=FailingBedrockClient())
    app.dependency_overrides[get_resolution_agent] = lambda: ResolutionAgent(bedrock_client=FailingBedrockClient())

    with caplog.at_level(logging.INFO, logger="agentflow.api"):
        response = client.post("/api/cases/resolve", json={"customer_id": customer.id, "message": "My item arrived broken"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "escalated"
    assert body["resolution_reason"] == "System failure - manual review required"

    case = db_session.query(Case).filter_by(id=body["case_id"]).one()
    assert case.status == "escalated"
    assert case.status != "processing"
    assert case.escalation_reason == "System failure - manual review required"

    assert any("run_case failed" in record.message for record in caplog.records)
