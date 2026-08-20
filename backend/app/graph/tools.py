from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, Customer, Order, Policy

ALLOWED_ACTIONS = {"REFUND", "REPLACEMENT"}
CLOSED_STATUSES = {"resolved", "escalated"}


def _ok(data: dict) -> dict:
    return {"success": True, "data": data, "error": None}


def _fail(error: str) -> dict:
    return {"success": False, "data": None, "error": error}


def customer_lookup(db: Session, customer_id: int | None = None, email: str | None = None) -> dict:
    if customer_id is None and email is None:
        return _fail("customer_id or email is required")

    query = select(Customer)
    query = query.where(Customer.id == customer_id) if customer_id is not None else query.where(Customer.email == email)

    customer = db.execute(query).scalar_one_or_none()
    if customer is None:
        return _fail("customer not found")

    return _ok({
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
    })


def order_lookup(db: Session, order_id: int, customer_id: int | None = None) -> dict:
    order = db.get(Order, order_id)
    if order is None:
        return _fail("order not found")

    if customer_id is not None and order.customer_id != customer_id:
        return _fail("order does not belong to this customer")

    return _ok({
        "id": order.id,
        "customer_id": order.customer_id,
        "item_name": order.item_name,
        "status": order.status,
        "delivered_item": order.delivered_item,
        "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    })


def policy_lookup(db: Session, issue_type: str) -> dict:
    policy = db.execute(select(Policy).where(Policy.issue_type == issue_type)).scalar_one_or_none()
    if policy is None:
        return _fail(f"no policy found for issue_type '{issue_type}'")

    return _ok({
        "id": policy.id,
        "issue_type": policy.issue_type,
        "refund_allowed": policy.refund_allowed,
        "replacement_allowed": policy.replacement_allowed,
        "max_resolution_days": policy.max_resolution_days,
        "description": policy.description,
    })


def _case_summary(case: Case) -> dict:
    return {
        "id": case.id,
        "status": case.status,
        "resolution": case.resolution,
        "issue_type": case.issue_type,
        "action_reference": case.action_reference,
        "escalation_reason": case.escalation_reason,
    }


def resolution_action(db: Session, case_id: int, action: str) -> dict:
    if action not in ALLOWED_ACTIONS:
        return _fail(f"action must be one of {sorted(ALLOWED_ACTIONS)}")

    case = db.get(Case, case_id)
    if case is None:
        return _fail("case not found")

    if case.status in CLOSED_STATUSES:
        return _fail(f"case is already {case.status}")

    policy = db.execute(select(Policy).where(Policy.issue_type == case.issue_type)).scalar_one_or_none()
    if policy is None:
        return _fail(f"no policy found for issue_type '{case.issue_type}'")

    if action == "REFUND" and not policy.refund_allowed:
        return _fail("refund is not allowed for this issue type")
    if action == "REPLACEMENT" and not policy.replacement_allowed:
        return _fail("replacement is not allowed for this issue type")

    case.resolution = action
    case.status = "resolved"
    case.action_reference = f"ACT-{uuid4().hex[:10].upper()}"
    db.commit()
    db.refresh(case)

    return _ok(_case_summary(case))


def escalate_case(db: Session, case_id: int, reason: str) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        return _fail("case not found")

    if case.status in CLOSED_STATUSES:
        return _fail(f"case is already {case.status}")

    case.resolution = "ESCALATE"
    case.status = "escalated"
    case.escalation_reason = reason
    db.commit()
    db.refresh(case)

    return _ok(_case_summary(case))
