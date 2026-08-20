from typing import TypedDict

from app.graph.agents import InvestigationPlan, InvestigationResult, ReflectionResult, ResolutionResult


class CaseState(TypedDict):
    case_id: int
    customer_message: str
    customer_id: int | None
    plan: InvestigationPlan | None
    investigation: InvestigationResult | None
    reflection: ReflectionResult | None
    resolution: ResolutionResult | None
    action_result: dict | None
    verification_passed: bool | None
    final_response: str | None
