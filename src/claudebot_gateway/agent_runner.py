import logging
from pathlib import Path
from typing import Any

from claudebot_gateway.agent_runtime import AgentExecutionRequest, AgentRuntime
from claudebot_gateway.message_bus import MessageBus

_LOGGER = logging.getLogger("claudebot_gateway.agent_runner")


class AgentRunner:
    _SENDER_KEYS = ("sender", "sender_id", "source_key", "user_id")
    _SENSITIVE_TOKENS = ("token", "secret", "authorization", "password", "api_key", "cookie")

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        default_workspace: Path,
        channel_allowed_senders: dict[str, set[str]] | None = None,
    ):
        self._runtime = runtime
        self._default_workspace = Path(default_workspace)
        self._channel_allowed_senders = channel_allowed_senders or {}

    async def process_once(self, bus: MessageBus) -> dict[str, Any]:
        inbound = await bus.inbound.get()
        channel = str(inbound.get("channel", "cli"))
        destination = str(inbound.get("destination", "cli:stdout"))
        prompt = str(inbound.get("text", ""))
        workspace_raw = inbound.get("workspace")
        workspace = Path(workspace_raw) if isinstance(workspace_raw, str) else self._default_workspace
        _LOGGER.info(
            "agent_runner_inbound_received channel=%s destination=%s prompt_len=%s",
            channel,
            destination,
            len(prompt),
        )
        if not self._is_sender_allowed(channel=channel, inbound=inbound):
            outbound = {
                "channel": channel,
                "destination": destination,
                "text": "Sender is not allowed for this channel.",
            }
            await bus.publish_outbound(outbound)
            _LOGGER.info(
                "agent_runner_outbound_published channel=%s destination=%s reason=sender_not_allowed",
                channel,
                destination,
            )
            return outbound
        safe_metadata = self._sanitize_metadata(inbound)
        try:
            result = await self._runtime.execute(
                AgentExecutionRequest(
                    prompt=prompt,
                    workspace=workspace,
                    channel=channel,
                    destination=destination,
                    metadata=safe_metadata,
                )
            )
            text = result.text
            _LOGGER.info(
                "agent_runner_runtime_succeeded channel=%s destination=%s response_len=%s",
                channel,
                destination,
                len(text),
            )
        except Exception:
            _LOGGER.exception(
                "agent_runner_runtime_failed channel=%s destination=%s",
                channel,
                destination,
            )
            text = "Agent execution failed. Try again shortly."
        outbound = {
            "channel": channel,
            "destination": destination,
            "text": text,
        }
        await bus.publish_outbound(outbound)
        _LOGGER.info(
            "agent_runner_outbound_published channel=%s destination=%s response_len=%s",
            channel,
            destination,
            len(text),
        )
        return outbound

    def _is_sender_allowed(self, *, channel: str, inbound: dict[str, Any]) -> bool:
        allowed_senders = self._channel_allowed_senders.get(channel)
        if not allowed_senders:
            return True
        sender = self._extract_sender(inbound)
        if sender is None:
            return False
        return sender in allowed_senders

    def _extract_sender(self, inbound: dict[str, Any]) -> str | None:
        for key in self._SENDER_KEYS:
            value = inbound.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _sanitize_metadata(self, inbound: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in inbound.items():
            key_lower = key.lower()
            if any(token in key_lower for token in self._SENSITIVE_TOKENS):
                continue
            if isinstance(value, str | int | float | bool) or value is None:
                sanitized[key] = value
        return sanitized
