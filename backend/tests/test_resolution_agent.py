import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.graph.agents import InvestigationResult, ResolutionAgent
from app.models import Policy


class FakeBedrockClient:
    def __init__(self, response):
        self._response = response

    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        if isinstance(self._response, dict):
            return json.dumps(self._response)
        return self._response


class UnusedBedrockClient:
    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        raise AssertionError("Bedrock should not be called")


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def policies(db):
    damaged = Policy(issue_type="damaged_order", refund_allowed=True, replacement_allowed=True, max_resolution_days=5, description="Damaged order policy")
    missing = Policy(issue_type="missing_delivery", refund_allowed=True, replacement_allowed=False, max_resolution_days=7, description="Missing delivery policy")
    wrong = Policy(issue_type="wrong_item", refund_allowed=False, replacement_allowed=True, max_resolution_days=5, description="Wrong item policy")
    db.add_all([damaged, missing, wrong])
    db.commit()
    return {"damaged_order": damaged, "missing_delivery": missing, "wrong_item": wrong}


def run(coro):
    return asyncio.run(coro)


DELIVERY_DATE = "2026-08-01T00:00:00+00:00"
WITHIN_WINDOW_NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)   # 2 days after delivery, limit is 5
OUTSIDE_WINDOW_NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)  # 9 days after delivery, limit is 5


def _completed_investigation(issue_type: str, delivery_date: str | None = DELIVERY_DATE) -> InvestigationResult:
    return InvestigationResult(
        issue_type=issue_type,
        customer_id=1,
        order_id=101,
        evidence={"order": {"id": 101, "status": "delivered_damaged", "delivery_date": delivery_date}},
        missing_information=[],
        investigation_complete=True,
    )


def test_damaged_order_valid_refund(db, policies):
    bedrock = FakeBedrockClient({"decision": "REFUND", "reason": "item confirmed damaged"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("damaged_order"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "REFUND"
    assert result.ready_for_action is True
    assert result.policy["issue_type"] == "damaged_order"


def test_damaged_order_valid_replacement(db, policies):
    bedrock = FakeBedrockClient({"decision": "REPLACEMENT", "reason": "customer prefers a replacement"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("damaged_order"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "REPLACEMENT"
    assert result.ready_for_action is True


def test_wrong_item_replacement(db, policies):
    bedrock = FakeBedrockClient({"decision": "REPLACEMENT", "reason": "send the correct item"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("wrong_item"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "REPLACEMENT"
    assert result.ready_for_action is True


def test_disallowed_refund_forces_escalation(db, policies):
    bedrock = FakeBedrockClient({"decision": "REFUND", "reason": "customer wants a refund"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("wrong_item"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False
    assert "not allowed" in result.reason


def test_missing_delivery_refund(db, policies):
    bedrock = FakeBedrockClient({"decision": "REFUND", "reason": "package lost"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("missing_delivery", delivery_date=None), now=WITHIN_WINDOW_NOW))

    assert result.decision == "REFUND"
    assert result.ready_for_action is True


def test_incomplete_investigation_escalates(db, policies):
    agent = ResolutionAgent(bedrock_client=UnusedBedrockClient())
    investigation = InvestigationResult(
        issue_type="damaged_order",
        customer_id=1,
        order_id=None,
        evidence={},
        missing_information=["order_id"],
        investigation_complete=False,
    )

    result = run(agent.resolve(db, investigation))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False


def test_missing_policy_escalates(db):
    agent = ResolutionAgent(bedrock_client=UnusedBedrockClient())

    result = run(agent.resolve(db, _completed_investigation("wrong_item"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False
    assert "no policy found" in result.reason


def test_malformed_llm_response_escalates(db, policies):
    bedrock = FakeBedrockClient("not valid json")
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("damaged_order"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False


def test_unsupported_decision_value_escalates(db, policies):
    bedrock = FakeBedrockClient({"decision": "REFUND_NOW", "reason": "not a real decision"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("damaged_order"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False


def test_damaged_order_within_resolution_window(db, policies):
    bedrock = FakeBedrockClient({"decision": "REFUND", "reason": "item confirmed damaged"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    result = run(agent.resolve(db, _completed_investigation("damaged_order"), now=WITHIN_WINDOW_NOW))

    assert result.decision == "REFUND"
    assert result.ready_for_action is True


def test_damaged_order_outside_resolution_window(db, policies):
    agent = ResolutionAgent(bedrock_client=UnusedBedrockClient())

    result = run(agent.resolve(db, _completed_investigation("damaged_order"), now=OUTSIDE_WINDOW_NOW))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False
    assert "resolution window" in result.reason


def test_wrong_item_outside_resolution_window(db, policies):
    agent = ResolutionAgent(bedrock_client=UnusedBedrockClient())

    result = run(agent.resolve(db, _completed_investigation("wrong_item"), now=OUTSIDE_WINDOW_NOW))

    assert result.decision == "ESCALATE"
    assert result.ready_for_action is False
    assert "resolution window" in result.reason


def test_missing_delivery_not_rejected_for_null_delivery_date(db, policies):
    bedrock = FakeBedrockClient({"decision": "REFUND", "reason": "package lost"})
    agent = ResolutionAgent(bedrock_client=bedrock)

    far_future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    investigation = _completed_investigation("missing_delivery", delivery_date=None)

    result = run(agent.resolve(db, investigation, now=far_future))

    assert result.decision == "REFUND"
    assert result.ready_for_action is True
