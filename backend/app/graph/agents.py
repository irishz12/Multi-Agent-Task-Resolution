import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.bedrock_client import BedrockClient
from app.graph.tools import customer_lookup, order_lookup, policy_lookup

IssueType = Literal["damaged_order", "missing_delivery", "wrong_item"]
Decision = Literal["REFUND", "REPLACEMENT", "ESCALATE"]

ALLOWED_TOOLS = {"customer_lookup", "order_lookup"}

PLANNER_SYSTEM_PROMPT = """You plan how to investigate a customer support message for an online retailer.

You do not investigate anything yourself and you do not decide on a resolution.
You only produce a short plan for the steps that follow you.

Respond with JSON only, no other text, in this exact shape:
{"goal": "<one short sentence>", "required_steps": [<short step names>], "required_tools": [<tool names>]}

required_tools may only contain "customer_lookup" and "order_lookup"."""


class InvestigationPlan(BaseModel):
    goal: str
    required_steps: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)

    @field_validator("required_tools")
    @classmethod
    def _keep_allowed_tools_only(cls, value: list[str]) -> list[str]:
        return [name for name in dict.fromkeys(value) if name in ALLOWED_TOOLS]


class Planner:
    def __init__(self, bedrock_client: BedrockClient | None = None):
        self._bedrock = bedrock_client or BedrockClient()

    async def plan(self, customer_message: str) -> InvestigationPlan:
        response = await self._bedrock.chat(
            [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": customer_message},
            ]
        )

        try:
            data = json.loads(_strip_code_fence(response))
            return InvestigationPlan.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return InvestigationPlan(goal="Investigate and resolve the customer's issue")


class ReflectionResult(BaseModel):
    complete: bool
    missing_information: list[str]
    should_continue: bool


def reflect(investigation: "InvestigationResult") -> ReflectionResult:
    return ReflectionResult(
        complete=investigation.investigation_complete,
        missing_information=investigation.missing_information,
        should_continue=investigation.investigation_complete,
    )


EXTRACTION_SYSTEM_PROMPT = """You investigate customer support messages for an online retailer.

Supported issue types are exactly:
- damaged_order: the item arrived broken or damaged
- missing_delivery: the order never arrived or is lost
- wrong_item: the customer received a different item than ordered

You have two lookup tools available: "customer_lookup" and "order_lookup".
Decide which of them are actually needed to investigate this message.

Respond with JSON only, no other text, in this exact shape:
{"issue_type": "damaged_order" | "missing_delivery" | "wrong_item" | null, "order_id": <integer or null>, "requested_tools": [<tool names>]}

Use null for issue_type if the message does not clearly match one of the three types.
Use null for order_id if no order number is mentioned.
Only include tool names you actually need in requested_tools."""


class ExtractedIssue(BaseModel):
    issue_type: IssueType | None = None
    order_id: int | None = None
    requested_tools: list[str] = Field(default_factory=list)

    @field_validator("requested_tools")
    @classmethod
    def _keep_allowed_tools_only(cls, value: list[str]) -> list[str]:
        return [name for name in dict.fromkeys(value) if name in ALLOWED_TOOLS]


class InvestigationResult(BaseModel):
    issue_type: IssueType | None
    customer_id: int | None
    order_id: int | None
    evidence: dict
    missing_information: list[str]
    investigation_complete: bool


class InvestigationAgent:
    def __init__(self, bedrock_client: BedrockClient | None = None):
        self._bedrock = bedrock_client or BedrockClient()

    async def investigate(self, db: Session, customer_message: str, customer_id: int | None = None) -> InvestigationResult:
        extracted = await self._extract_issue(customer_message)
        evidence: dict = {}
        missing: list[str] = []

        if "customer_lookup" in extracted.requested_tools:
            if customer_id is None:
                missing.append("customer_id")
            else:
                result = customer_lookup(db, customer_id=customer_id)
                if result["success"]:
                    evidence["customer"] = result["data"]
                else:
                    missing.append(result["error"])

        if "order_lookup" in extracted.requested_tools:
            if extracted.order_id is None:
                missing.append("order_id")
            else:
                result = order_lookup(db, order_id=extracted.order_id, customer_id=customer_id)
                if result["success"]:
                    evidence["order"] = result["data"]
                else:
                    missing.append(result["error"])

        if extracted.issue_type is None:
            missing.append("issue_type")

        return InvestigationResult(
            issue_type=extracted.issue_type,
            customer_id=customer_id,
            order_id=extracted.order_id,
            evidence=evidence,
            missing_information=missing,
            investigation_complete=not missing,
        )

    async def _extract_issue(self, customer_message: str) -> ExtractedIssue:
        response = await self._bedrock.chat(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": customer_message},
            ]
        )

        try:
            data = json.loads(_strip_code_fence(response))
            return ExtractedIssue.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return ExtractedIssue()


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


RESOLUTION_SYSTEM_PROMPT = """You decide how to resolve a customer support case for an online retailer.

You will be given the investigation evidence and the applicable policy as JSON.
Choose exactly one decision: REFUND, REPLACEMENT, or ESCALATE.
Only choose REFUND or REPLACEMENT if the policy allows it and the evidence supports it.
Choose ESCALATE if you are unsure or the policy does not clearly allow an automatic resolution.

Respond with JSON only, no other text, in this exact shape:
{"decision": "REFUND" | "REPLACEMENT" | "ESCALATE", "reason": "<short reason>"}"""


class ProposedDecision(BaseModel):
    decision: Decision = "ESCALATE"
    reason: str = ""


class ResolutionResult(BaseModel):
    decision: Decision
    reason: str
    policy: dict
    ready_for_action: bool


# Issue types where the order's delivery_date bounds the resolution window.
# missing_delivery has no delivery_date, so it is excluded.
DELIVERY_WINDOW_ISSUE_TYPES = {"damaged_order", "wrong_item"}


def _outside_resolution_window(delivery_date: str | None, max_resolution_days: int | None, now: datetime) -> bool:
    if delivery_date is None or max_resolution_days is None:
        return False
    delivered_at = datetime.fromisoformat(delivery_date)
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=timezone.utc)
    return (now - delivered_at).days > max_resolution_days


class ResolutionAgent:
    def __init__(self, bedrock_client: BedrockClient | None = None):
        self._bedrock = bedrock_client or BedrockClient()

    async def resolve(self, db: Session, investigation: InvestigationResult, now: datetime | None = None) -> ResolutionResult:
        now = now or datetime.now(timezone.utc)

        if not investigation.investigation_complete or investigation.issue_type is None:
            return ResolutionResult(decision="ESCALATE", reason="investigation is incomplete", policy={}, ready_for_action=False)

        policy_result = policy_lookup(db, issue_type=investigation.issue_type)
        if not policy_result["success"]:
            return ResolutionResult(decision="ESCALATE", reason=policy_result["error"], policy={}, ready_for_action=False)

        policy = policy_result["data"]

        if investigation.issue_type in DELIVERY_WINDOW_ISSUE_TYPES:
            delivery_date = investigation.evidence.get("order", {}).get("delivery_date")
            if _outside_resolution_window(delivery_date, policy["max_resolution_days"], now):
                return ResolutionResult(decision="ESCALATE", reason="request is outside the policy resolution window", policy=policy, ready_for_action=False)

        proposed = await self._propose_decision(investigation, policy)

        if proposed.decision == "REFUND" and not policy["refund_allowed"]:
            return ResolutionResult(decision="ESCALATE", reason="refund is not allowed by policy", policy=policy, ready_for_action=False)
        if proposed.decision == "REPLACEMENT" and not policy["replacement_allowed"]:
            return ResolutionResult(decision="ESCALATE", reason="replacement is not allowed by policy", policy=policy, ready_for_action=False)

        return ResolutionResult(
            decision=proposed.decision,
            reason=proposed.reason,
            policy=policy,
            ready_for_action=proposed.decision in ("REFUND", "REPLACEMENT"),
        )

    async def _propose_decision(self, investigation: InvestigationResult, policy: dict) -> ProposedDecision:
        payload = json.dumps({
            "issue_type": investigation.issue_type,
            "evidence": investigation.evidence,
            "policy": policy,
        })
        response = await self._bedrock.chat(
            [
                {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ]
        )

        try:
            data = json.loads(_strip_code_fence(response))
            return ProposedDecision.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return ProposedDecision(decision="ESCALATE", reason="unable to parse resolution decision")
