import asyncio
import logging
from pathlib import Path

from claudebot_gateway.message_bus import MessageBus


def test_inbound_generates_outbound_with_target_channel(collecting_adapter, echo_runtime):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    async def _run() -> list[dict[str, str]]:
        bus = MessageBus()
        runner = AgentRunner(runtime=echo_runtime, default_workspace=Path("workspaces/main"))
        dispatcher = OutboundDispatcher(adapters={"telegram": collecting_adapter})
        await bus.publish_inbound({"channel": "telegram", "destination": "chat:1", "text": "hi"})
        await runner.process_once(bus)
        await dispatcher.dispatch_once(bus)
        return collecting_adapter.sent

    sent = asyncio.run(_run())
    assert sent[0]["channel"] == "telegram"
    assert sent[0]["destination"] == "chat:1"
    assert sent[0]["text"] == "echo:hi"


def test_runtime_failure_still_emits_routed_outbound_message(failing_runtime):
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> dict[str, str]:
        bus = MessageBus()
        runner = AgentRunner(runtime=failing_runtime, default_workspace=Path("workspaces/main"))
        await bus.publish_inbound({"channel": "telegram", "destination": "chat:9", "text": "hi"})
        return await runner.process_once(bus)

    outbound = asyncio.run(_run())
    assert outbound["channel"] == "telegram"
    assert outbound["destination"] == "chat:9"
    assert outbound["text"] == "Agent execution failed. Try again shortly."


def test_sender_not_in_allow_list_is_rejected_without_runtime_call(tracking_runtime):
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> tuple[dict[str, str], int]:
        bus = MessageBus()
        runner = AgentRunner(
            runtime=tracking_runtime,
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
        return outbound, len(tracking_runtime.requests)

    outbound, request_count = asyncio.run(_run())
    assert request_count == 0
    assert outbound["text"] == "Sender is not allowed for this channel."


def test_runtime_metadata_is_sanitized_before_execution(tracking_runtime):
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> dict[str, object]:
        bus = MessageBus()
        runner = AgentRunner(runtime=tracking_runtime, default_workspace=Path("workspaces/main"))
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
        metadata = tracking_runtime.requests[0].metadata or {}
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


def test_dispatch_flow_emits_observability_logs(collecting_adapter, echo_runtime, caplog):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    async def _run() -> None:
        bus = MessageBus()
        runner = AgentRunner(runtime=echo_runtime, default_workspace=Path("workspaces/main"))
        dispatcher = OutboundDispatcher(adapters={"feishu": collecting_adapter})
        await bus.publish_inbound({"channel": "feishu", "destination": "oc_test", "text": "hello"})
        await runner.process_once(bus)
        await dispatcher.dispatch_once(bus)

    caplog.set_level(logging.INFO)
    asyncio.run(_run())
    messages = [record.getMessage() for record in caplog.records]
    assert any("agent_runner_inbound_received" in message for message in messages)
    assert any("agent_runner_outbound_published" in message for message in messages)
    assert any("outbound_dispatched" in message for message in messages)
