import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.graph.agents import InvestigationAgent, Planner, ResolutionAgent
from app.graph.graph import run_case
from app.graph.tools import customer_lookup, escalate_case
from app.models import Case
from app.routes.workflow_summary import InvestigationPlanOut, ReflectionOut, WorkflowStepOut, build_workflow_summary

logger = logging.getLogger("agentflow.api")

router = APIRouter(prefix="/api/cases", tags=["cases"])

SYSTEM_FAILURE_REASON = "System failure - manual review required"


def get_planner() -> Planner:
    return Planner()


def get_investigation_agent() -> InvestigationAgent:
    return InvestigationAgent()


def get_resolution_agent() -> ResolutionAgent:
    return ResolutionAgent()


class ResolveCaseRequest(BaseModel):
    customer_id: int
    message: str


class ResolveCaseResponse(BaseModel):
    case_id: int
    issue_type: str | None
    resolution: str | None
    status: str
    action_reference: str | None
    message: str
    # Added for LangGraph execution visibility. Existing clients reading only
    # the fields above are unaffected — these are additive and optional.
    plan: InvestigationPlanOut | None = None
    reflection: ReflectionOut | None = None
    steps: list[WorkflowStepOut] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    resolution_reason: str | None = None


class CaseDetail(BaseModel):
    case_id: int
    customer_message: str
    customer_id: int | None
    order_id: int | None
    issue_type: str | None
    resolution: str | None
    status: str
    action_reference: str | None
    escalation_reason: str | None


@router.post("/resolve", response_model=ResolveCaseResponse)
async def resolve_case(
    payload: ResolveCaseRequest,
    db: Session = Depends(get_db),
    planner: Planner = Depends(get_planner),
    investigation_agent: InvestigationAgent = Depends(get_investigation_agent),
    resolution_agent: ResolutionAgent = Depends(get_resolution_agent),
):
    customer_result = customer_lookup(db, customer_id=payload.customer_id)
    if not customer_result["success"]:
        raise HTTPException(status_code=404, detail=customer_result["error"])

    case = Case(customer_message=payload.message, customer_id=payload.customer_id, status="processing")
    db.add(case)
    db.commit()
    db.refresh(case)

    try:
        final_state = await run_case(
            db,
            case_id=case.id,
            customer_message=payload.message,
            customer_id=payload.customer_id,
            planner=planner,
            investigation_agent=investigation_agent,
            resolution_agent=resolution_agent,
        )
    except Exception as exc:
        logger.exception("case_id=%s run_case failed, escalating: %s", case.id, exc)
        escalate_case(db, case_id=case.id, reason=SYSTEM_FAILURE_REASON)
        db.refresh(case)
        return ResolveCaseResponse(
            case_id=case.id,
            issue_type=case.issue_type,
            resolution=case.resolution,
            status=case.status,
            action_reference=case.action_reference,
            message=f"Case escalated: {SYSTEM_FAILURE_REASON}",
            resolution_reason=SYSTEM_FAILURE_REASON,
        )

    db.refresh(case)

    steps, tools_used = build_workflow_summary(final_state, case.status)
    plan = final_state.get("plan")
    reflection = final_state.get("reflection")
    resolution = final_state.get("resolution")

    return ResolveCaseResponse(
        case_id=case.id,
        issue_type=case.issue_type,
        resolution=case.resolution,
        status=case.status,
        action_reference=case.action_reference,
        message=final_state["final_response"],
        plan=InvestigationPlanOut(**plan.model_dump()) if plan else None,
        reflection=ReflectionOut(**reflection.model_dump()) if reflection else None,
        steps=steps,
        tools_used=tools_used,
        resolution_reason=resolution.reason if resolution else None,
    )


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    return CaseDetail(
        case_id=case.id,
        customer_message=case.customer_message,
        customer_id=case.customer_id,
        order_id=case.order_id,
        issue_type=case.issue_type,
        resolution=case.resolution,
        status=case.status,
        action_reference=case.action_reference,
        escalation_reason=case.escalation_reason,
    )
