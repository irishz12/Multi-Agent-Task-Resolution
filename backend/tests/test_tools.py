import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.graph.tools import (
    customer_lookup,
    escalate_case,
    order_lookup,
    policy_lookup,
    resolution_action,
)
from app.models import Case, Customer, Order, Policy


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

    order = Order(customer_id=customer.id, item_name="Headphones", status="delivered")
    db.add(order)
    db.flush()

    damaged_policy = Policy(
        issue_type="damaged_order",
        refund_allowed=True,
        replacement_allowed=False,
        description="Damaged order policy",
    )
    strict_policy = Policy(
        issue_type="missing_delivery",
        refund_allowed=False,
        replacement_allowed=False,
        description="Missing delivery, no auto resolution",
    )
    db.add_all([damaged_policy, strict_policy])
    db.flush()

    case = Case(
        customer_message="My item arrived broken",
        customer_id=customer.id,
        order_id=order.id,
        issue_type="damaged_order",
        status="open",
    )
    blocked_case = Case(
        customer_message="Package never came",
        customer_id=customer.id,
        order_id=order.id,
        issue_type="missing_delivery",
        status="open",
    )
    db.add_all([case, blocked_case])
    db.commit()

    return {
        "customer": customer,
        "other_customer": other_customer,
        "order": order,
        "case": case,
        "blocked_case": blocked_case,
    }


def test_customer_lookup_success(db, sample_data):
    result = customer_lookup(db, customer_id=sample_data["customer"].id)
    assert result["success"] is True
    assert result["data"]["email"] == "jane@example.com"


def test_customer_lookup_not_found(db, sample_data):
    result = customer_lookup(db, customer_id=999)
    assert result["success"] is False
    assert result["error"] == "customer not found"


def test_order_lookup_success(db, sample_data):
    result = order_lookup(db, order_id=sample_data["order"].id)
    assert result["success"] is True
    assert result["data"]["item_name"] == "Headphones"


def test_order_lookup_ownership_mismatch(db, sample_data):
    result = order_lookup(db, order_id=sample_data["order"].id, customer_id=sample_data["other_customer"].id)
    assert result["success"] is False
    assert "belong" in result["error"]


def test_policy_lookup_success(db, sample_data):
    result = policy_lookup(db, issue_type="damaged_order")
    assert result["success"] is True
    assert result["data"]["refund_allowed"] is True


def test_resolution_action_allowed(db, sample_data):
    result = resolution_action(db, case_id=sample_data["case"].id, action="REFUND")
    assert result["success"] is True
    assert result["data"]["status"] == "resolved"
    assert result["data"]["action_reference"].startswith("ACT-")


def test_resolution_action_disallowed_by_policy(db, sample_data):
    result = resolution_action(db, case_id=sample_data["blocked_case"].id, action="REFUND")
    assert result["success"] is False
    assert "not allowed" in result["error"]


def test_resolution_action_duplicate_blocked(db, sample_data):
    resolution_action(db, case_id=sample_data["case"].id, action="REFUND")
    result = resolution_action(db, case_id=sample_data["case"].id, action="REFUND")
    assert result["success"] is False
    assert "already" in result["error"]


def test_escalate_case_success(db, sample_data):
    result = escalate_case(db, case_id=sample_data["blocked_case"].id, reason="policy does not allow refund")
    assert result["success"] is True
    assert result["data"]["status"] == "escalated"


def test_escalate_case_duplicate_blocked(db, sample_data):
    escalate_case(db, case_id=sample_data["blocked_case"].id, reason="policy does not allow refund")
    result = escalate_case(db, case_id=sample_data["blocked_case"].id, reason="trying again")
    assert result["success"] is False
    assert "already" in result["error"]
