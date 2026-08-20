import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.graph.agents import InvestigationAgent
from app.models import Customer, Order


class FakeBedrockClient:
    def __init__(self, response: dict):
        self._response = response

    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        return json.dumps(self._response)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def sample_data(db):
    customer = Customer(name="Jane Doe", email="jane@example.com")
    other_customer = Customer(name="John Roe", email="john@example.com")
    db.add_all([customer, other_customer])
    db.flush()

    damaged_order = Order(customer_id=customer.id, item_name="Widget", status="delivered_damaged", delivered_item="Widget")
    lost_order = Order(customer_id=customer.id, item_name="Gadget", status="lost")
    wrong_item_order = Order(customer_id=customer.id, item_name="Blue Mug", status="delivered", delivered_item="Red Mug")
    other_order = Order(customer_id=other_customer.id, item_name="Lamp", status="delivered")
    db.add_all([damaged_order, lost_order, wrong_item_order, other_order])
    db.commit()

    return {
        "customer": customer,
        "other_customer": other_customer,
        "damaged_order": damaged_order,
        "lost_order": lost_order,
        "wrong_item_order": wrong_item_order,
        "other_order": other_order,
    }


def run(coro):
    return asyncio.run(coro)


def test_damaged_order_investigation(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": sample_data["damaged_order"].id,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.issue_type == "damaged_order"
    assert result.investigation_complete is True
    assert result.evidence["order"]["status"] == "delivered_damaged"
    assert result.missing_information == []


def test_missing_delivery_investigation(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "missing_delivery",
        "order_id": sample_data["lost_order"].id,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My package never showed up", customer_id=sample_data["customer"].id))

    assert result.issue_type == "missing_delivery"
    assert result.investigation_complete is True
    assert result.evidence["order"]["status"] == "lost"


def test_wrong_item_investigation(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "wrong_item",
        "order_id": sample_data["wrong_item_order"].id,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "I got a red mug instead of a blue one", customer_id=sample_data["customer"].id))

    assert result.issue_type == "wrong_item"
    assert result.investigation_complete is True
    assert result.evidence["order"]["delivered_item"] == "Red Mug"


def test_missing_order_id(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": None,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.investigation_complete is False
    assert "order_id" in result.missing_information


def test_nonexistent_order(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": 9999,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.investigation_complete is False
    assert "order not found" in result.missing_information


def test_customer_order_mismatch(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": sample_data["other_order"].id,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.investigation_complete is False
    assert any("belong" in item for item in result.missing_information)


def test_requests_only_order_lookup(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": sample_data["damaged_order"].id,
        "requested_tools": ["order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.investigation_complete is True
    assert "order" in result.evidence
    assert "customer" not in result.evidence


def test_requests_customer_and_order_lookup(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": sample_data["damaged_order"].id,
        "requested_tools": ["customer_lookup", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.investigation_complete is True
    assert "customer" in result.evidence
    assert "order" in result.evidence


def test_unsupported_tool_name_is_ignored(db, sample_data):
    bedrock = FakeBedrockClient({
        "issue_type": "damaged_order",
        "order_id": sample_data["damaged_order"].id,
        "requested_tools": ["customer_lookup", "delete_database", "order_lookup"],
    })
    agent = InvestigationAgent(bedrock_client=bedrock)

    result = run(agent.investigate(db, "My item arrived broken", customer_id=sample_data["customer"].id))

    assert result.investigation_complete is True
    assert set(result.evidence.keys()) == {"customer", "order"}
