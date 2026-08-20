import logging
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.orm import Session

from app.graph.agents import InvestigationAgent, Planner, ResolutionAgent, reflect
from app.graph.state import CaseState
from app.graph.tools import escalate_case, resolution_action
from app.models import Case

logger = logging.getLogger("agentflow.graph")


@dataclass
class GraphContext:
    db: Session
    planner: Planner
    investigation_agent: InvestigationAgent
    resolution_agent: ResolutionAgent


async def planner_node(state: CaseState, runtime: Runtime[GraphContext]) -> dict:
    plan = await runtime.context.planner.plan(state["customer_message"])
    logger.info("case_id=%s agent=planner goal=%r", state["case_id"], plan.goal)
    return {"plan": plan}


async def investigate_node(state: CaseState, runtime: Runtime[GraphContext]) -> dict:
    context = runtime.context
    result = await context.investigation_agent.investigate(
        context.db, state["customer_message"], state["customer_id"]
    )
    logger.info(
        "case_id=%s agent=investigation issue_type=%s missing=%s",
        state["case_id"], result.issue_type, result.missing_information,
    )
    _persist_issue_type(context.db, state["case_id"], result.issue_type)
    return {"investigation": result}


def _persist_issue_type(db: Session, case_id: int, issue_type: str | None) -> None:
    if issue_type is None:
        return
    case = db.get(Case, case_id)
    if case is not None:
        case.issue_type = issue_type
        db.commit()


def reflection_node(state: CaseState) -> dict:
    result = reflect(state["investigation"])
    logger.info("case_id=%s node=reflection complete=%s should_continue=%s", state["case_id"], result.complete, result.should_continue)
    return {"reflection": result}


def route_after_reflection(state: CaseState) -> str:
    return "resolve" if state["reflection"].should_continue else "escalate"


async def resolve_node(state: CaseState, runtime: Runtime[GraphContext]) -> dict:
    context = runtime.context
    result = await context.resolution_agent.resolve(context.db, state["investigation"])
    logger.info("case_id=%s agent=resolution decision=%s reason=%r", state["case_id"], result.decision, result.reason)
    return {"resolution": result}


def route_after_resolve(state: CaseState) -> str:
    if state["resolution"].decision in ("REFUND", "REPLACEMENT"):
        return "execute_action"
    return "escalate"


async def execute_action_node(state: CaseState, runtime: Runtime[GraphContext]) -> dict:
    result = resolution_action(runtime.context.db, case_id=state["case_id"], action=state["resolution"].decision)
    logger.info("case_id=%s tool=resolution_action success=%s", state["case_id"], result["success"])
    return {"action_result": result}


def verify_action_node(state: CaseState) -> dict:
    action_result = state["action_result"] or {}
    data = action_result.get("data") or {}
    passed = (
        action_result.get("success") is True
        and data.get("resolution") == state["resolution"].decision
        and bool(data.get("action_reference"))
    )
    return {"verification_passed": passed}


def route_after_verify(state: CaseState) -> str:
    return "respond" if state["verification_passed"] else "escalate"


async def escalate_node(state: CaseState, runtime: Runtime[GraphContext]) -> dict:
    reason = _escalation_reason(state)
    result = escalate_case(runtime.context.db, case_id=state["case_id"], reason=reason)
    logger.info("case_id=%s tool=escalate_case reason=%r success=%s", state["case_id"], reason, result["success"])
    return {"action_result": result}


def _escalation_reason(state: CaseState) -> str:
    action_result = state.get("action_result")
    if action_result and not action_result.get("success"):
        return action_result.get("error") or "resolution action failed"

    reflection = state.get("reflection")
    if reflection and not reflection.complete:
        missing = ", ".join(reflection.missing_information) or "required evidence"
        return f"investigation incomplete: missing {missing}"

    resolution = state.get("resolution")
    return resolution.reason if resolution else "escalated"


def respond_node(state: CaseState) -> dict:
    action_result = state.get("action_result") or {}
    data = action_result.get("data") or {}
    if action_result.get("success") and data.get("status") == "resolved":
        message = f"Case resolved: {data.get('resolution')} (reference {data.get('action_reference')})"
    elif action_result.get("success") and data.get("status") == "escalated":
        message = f"Case escalated: {data.get('escalation_reason')}"
    else:
        message = "Case escalated: unable to confirm resolution"
    return {"final_response": message}


def _build_graph():
    graph = StateGraph(CaseState, context_schema=GraphContext)

    graph.add_node("planner", planner_node)
    graph.add_node("investigate", investigate_node)
    graph.add_node("reflection", reflection_node)
    graph.add_node("resolve", resolve_node)
    graph.add_node("execute_action", execute_action_node)
    graph.add_node("verify_action", verify_action_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("respond", respond_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "investigate")
    graph.add_edge("investigate", "reflection")
    graph.add_conditional_edges(
        "reflection", route_after_reflection, {"resolve": "resolve", "escalate": "escalate"}
    )
    graph.add_conditional_edges(
        "resolve", route_after_resolve, {"execute_action": "execute_action", "escalate": "escalate"}
    )
    graph.add_edge("execute_action", "verify_action")
    graph.add_conditional_edges(
        "verify_action", route_after_verify, {"respond": "respond", "escalate": "escalate"}
    )
    graph.add_edge("escalate", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


compiled_graph = _build_graph()


async def run_case(
    db: Session,
    case_id: int,
    customer_message: str,
    customer_id: int | None = None,
    planner: Planner | None = None,
    investigation_agent: InvestigationAgent | None = None,
    resolution_agent: ResolutionAgent | None = None,
) -> CaseState:
    context = GraphContext(
        db=db,
        planner=planner or Planner(),
        investigation_agent=investigation_agent or InvestigationAgent(),
        resolution_agent=resolution_agent or ResolutionAgent(),
    )
    initial_state: CaseState = {
        "case_id": case_id,
        "customer_message": customer_message,
        "customer_id": customer_id,
        "plan": None,
        "investigation": None,
        "reflection": None,
        "resolution": None,
        "action_result": None,
        "verification_passed": None,
        "final_response": None,
    }
    return await compiled_graph.ainvoke(initial_state, context=context)
