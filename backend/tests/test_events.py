import asyncio
import json
from decimal import Decimal

import pytest

from signet.application.events import Event, EventBus


def test_fractional_agent_tool_arguments_are_json_safe_and_exact():
    event = Event(type="agent.intent", run_id="fractional", data={
        "raw_tool_args": {"amount": Decimal("123.000001")},
    })
    assert json.loads(event.to_json())["data"]["raw_tool_args"]["amount"] == "123.000001"


@pytest.mark.asyncio
async def test_replay_after_disconnect():
    bus = EventBus()
    await bus.publish(Event(type="run.started", run_id="run"))
    await bus.publish(Event(type="run.completed", run_id="run"))
    stream = bus.stream(last_event_id=1)
    event = await anext(stream)
    assert event.type == "run.completed"
    assert event.id == 2
    await stream.aclose()


@pytest.mark.asyncio
async def test_slow_subscriber_does_not_block_payment_events():
    bus = EventBus()
    stream = bus.stream(last_event_id=0)
    waiting = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await bus.publish(Event(type="first", run_id="run"))
    await waiting
    for _ in range(200):
        await asyncio.wait_for(bus.publish(Event(type="rule.check", run_id="run")), 0.5)
    await stream.aclose()
