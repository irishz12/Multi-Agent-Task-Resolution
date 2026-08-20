import asyncio
import json

from app.graph.agents import Planner


class FakeBedrockClient:
    def __init__(self, response):
        self._response = response

    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        if isinstance(self._response, dict):
            return json.dumps(self._response)
        return self._response


def run(coro):
    return asyncio.run(coro)


def test_plan_returns_goal_and_tools():
    planner = Planner(bedrock_client=FakeBedrockClient(
        {"goal": "Resolve the customer's issue", "required_steps": ["identify issue"], "required_tools": ["order_lookup"]}
    ))

    plan = run(planner.plan("My item arrived broken"))

    assert plan.goal == "Resolve the customer's issue"
    assert plan.required_tools == ["order_lookup"]


def test_plan_strips_unsupported_tool_names():
    planner = Planner(bedrock_client=FakeBedrockClient(
        {"goal": "Resolve the issue", "required_steps": [], "required_tools": ["customer_lookup", "delete_database", "order_lookup"]}
    ))

    plan = run(planner.plan("My item arrived broken"))

    assert plan.required_tools == ["customer_lookup", "order_lookup"]


def test_plan_falls_back_safely_on_malformed_response():
    planner = Planner(bedrock_client=FakeBedrockClient("not valid json"))

    plan = run(planner.plan("My item arrived broken"))

    assert plan.goal
    assert plan.required_tools == []
