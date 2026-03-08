import asyncio
from pathlib import Path

from claudebot_gateway.agent_runtime import AgentExecutionResult
from claudebot_gateway.message_bus import MessageBus


class _FakeAdapter:
    def __init__(self):
        self.sent: list[dict[str, str]] = []

    async def send(self, message: dict[str, str]) -> None:
        self.sent.append(message)


class _FakeRuntime:
    async def execute(self, request):
        return AgentExecutionResult(text=f"echo:{request.prompt}", provider="test")


class _FailingRuntime:
    async def execute(self, request):
        _ = request
        raise RuntimeError("boom")


def test_inbound_generates_outbound_with_target_channel():
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    async def _run() -> list[dict[str, str]]:
        bus = MessageBus()
        adapter = _FakeAdapter()
        runner = AgentRunner(runtime=_FakeRuntime(), default_workspace=Path("workspaces/main"))
        dispatcher = OutboundDispatcher(adapters={"telegram": adapter})
        await bus.publish_inbound({"channel": "telegram", "destination": "chat:1", "text": "hi"})
        await runner.process_once(bus)
        await dispatcher.dispatch_once(bus)
        return adapter.sent

    sent = asyncio.run(_run())
    assert sent[0]["channel"] == "telegram"
    assert sent[0]["destination"] == "chat:1"
    assert sent[0]["text"] == "echo:hi"


def test_runtime_failure_still_emits_routed_outbound_message():
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> dict[str, str]:
        bus = MessageBus()
        runner = AgentRunner(runtime=_FailingRuntime(), default_workspace=Path("workspaces/main"))
        await bus.publish_inbound({"channel": "telegram", "destination": "chat:9", "text": "hi"})
        return await runner.process_once(bus)

    outbound = asyncio.run(_run())
    assert outbound["channel"] == "telegram"
    assert outbound["destination"] == "chat:9"
    assert outbound["text"] == "Agent execution failed. Try again shortly."
