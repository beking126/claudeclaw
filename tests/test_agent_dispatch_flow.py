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


def test_metadata_sanitization_logs_dropped_fields(tracking_runtime, caplog):
    from claudebot_gateway.agent_runner import AgentRunner

    async def _run() -> None:
        bus = MessageBus()
        runner = AgentRunner(runtime=tracking_runtime, default_workspace=Path("workspaces/main"))
        await bus.publish_inbound({
            "channel": "cli",
            "destination": "cli:stdout",
            "text": "hi",
            "api_key": "leaked",
            "metadata": {"nested": "value"},
        })
        await runner.process_once(bus)

    caplog.set_level(logging.DEBUG)
    asyncio.run(_run())
    messages = [record.getMessage() for record in caplog.records]
    assert any("metadata_sensitive_keys_dropped" in m for m in messages)
    assert any("metadata_complex_values_dropped" in m for m in messages)


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


def test_dispatch_continues_after_adapter_send_failure(echo_runtime):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    class _FailingAdapter:
        async def send(self, message):
            raise RuntimeError("channel is down")

    async def _run() -> bool:
        bus = MessageBus()
        runner = AgentRunner(runtime=echo_runtime, default_workspace=Path("workspaces/main"))
        dispatcher = OutboundDispatcher(adapters={"telegram": _FailingAdapter()})
        await bus.publish_inbound({"channel": "telegram", "destination": "chat:1", "text": "hi"})
        await runner.process_once(bus)
        return await dispatcher.dispatch_once(bus)

    result = asyncio.run(_run())
    assert result is False


def test_workspace_traversal_falls_back_to_default(tracking_runtime):
    from claudebot_gateway.agent_runner import AgentRunner

    default_workspace = Path("workspaces/main")

    async def _run() -> Path:
        bus = MessageBus()
        runner = AgentRunner(runtime=tracking_runtime, default_workspace=default_workspace)
        await bus.publish_inbound({
            "channel": "cli",
            "destination": "cli:stdout",
            "text": "hi",
            "workspace": "../../etc",
        })
        await runner.process_once(bus)
        return tracking_runtime.requests[0].workspace

    used_workspace = asyncio.run(_run())
    assert used_workspace == default_workspace


def test_workspace_traversal_with_valid_subdirectory(tracking_runtime, tmp_path: Path):
    from claudebot_gateway.agent_runner import AgentRunner

    default_workspace = tmp_path / "workspaces" / "main"
    default_workspace.mkdir(parents=True, exist_ok=True)

    async def _run() -> Path:
        bus = MessageBus()
        runner = AgentRunner(runtime=tracking_runtime, default_workspace=default_workspace)
        await bus.publish_inbound({
            "channel": "cli",
            "destination": "cli:stdout",
            "text": "hi",
            "workspace": "subproject",
        })
        await runner.process_once(bus)
        return tracking_runtime.requests[0].workspace

    used_workspace = asyncio.run(_run())
    assert used_workspace == (default_workspace / "subproject").resolve()


def test_workspace_path_uses_validate_workspace_path(monkeypatch, tracking_runtime, tmp_path: Path):
    from claudebot_gateway.agent_runner import AgentRunner

    default_workspace = tmp_path / "workspaces" / "main"
    default_workspace.mkdir(parents=True, exist_ok=True)
    calls = {"count": 0}

    def _validate(path: Path, root: Path) -> Path:
        calls["count"] += 1
        assert root == default_workspace
        return path.resolve()

    monkeypatch.setattr("claudebot_gateway.agent_runner.validate_workspace_path", _validate)

    async def _run() -> Path:
        bus = MessageBus()
        runner = AgentRunner(runtime=tracking_runtime, default_workspace=default_workspace)
        await bus.publish_inbound(
            {
                "channel": "cli",
                "destination": "cli:stdout",
                "text": "hi",
                "workspace": "subproject",
            }
        )
        await runner.process_once(bus)
        return tracking_runtime.requests[0].workspace

    used_workspace = asyncio.run(_run())
    assert calls["count"] == 1
    assert used_workspace == (default_workspace / "subproject").resolve()
