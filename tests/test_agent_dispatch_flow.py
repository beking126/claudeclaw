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


class _TrackingRuntime:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return AgentExecutionResult(text=f"ok:{request.prompt}", provider="test")


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


def test_sender_not_in_allow_list_is_rejected_without_runtime_call():
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> tuple[dict[str, str], int]:
        bus = MessageBus()
        runtime = _TrackingRuntime()
        runner = AgentRunner(
            runtime=runtime,
            default_workspace=Path("workspaces/main"),
            channel_allowed_senders={"telegram": {"trusted-user"}},
        )
        await bus.publish_inbound(
            {
                "channel": "telegram",
                "destination": "chat:2",
                "sender": "untrusted-user",
                "text": "hi",
            }
        )
        outbound = await runner.process_once(bus)
        return outbound, len(runtime.requests)

    outbound, request_count = asyncio.run(_run())
    assert request_count == 0
    assert outbound["text"] == "Sender is not allowed for this channel."


def test_runtime_metadata_is_sanitized_before_execution():
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> dict[str, object]:
        bus = MessageBus()
        runtime = _TrackingRuntime()
        runner = AgentRunner(runtime=runtime, default_workspace=Path("workspaces/main"))
        await bus.publish_inbound(
            {
                "channel": "telegram",
                "destination": "chat:3",
                "sender": "trusted-user",
                "text": "hi",
                "token": "secret-token-value",
                "authorization": "Bearer abc",
                "extra": {"nested": "drop-me"},
                "meta_list": ["a", "b"],
                "count": 2,
            }
        )
        await runner.process_once(bus)
        metadata = runtime.requests[0].metadata or {}
        return metadata

    metadata = asyncio.run(_run())
    assert metadata["channel"] == "telegram"
    assert metadata["destination"] == "chat:3"
    assert metadata["sender"] == "trusted-user"
    assert metadata["count"] == 2
    assert "token" not in metadata
    assert "authorization" not in metadata
    assert "extra" not in metadata
    assert "meta_list" not in metadata
