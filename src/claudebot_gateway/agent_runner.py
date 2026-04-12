import logging
import time
from pathlib import Path
from typing import Any

from claudebot_gateway.agent_runtime import AgentExecutionRequest, AgentRuntime
from claudebot_gateway.message_bus import MessageBus
from claudebot_gateway.rate_limiter import SlidingWindowRateLimiter
from claudebot_gateway.workspaces import validate_workspace_path

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
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ):
        self._runtime = runtime
        self._default_workspace = Path(default_workspace)
        self._channel_allowed_senders = channel_allowed_senders or {}
        self._rate_limiter = rate_limiter

    async def process_once(self, bus: MessageBus) -> dict[str, Any]:
        inbound = await bus.inbound.get()
        channel = str(inbound.get("channel", "cli"))
        destination = str(inbound.get("destination", "cli:stdout"))
        prompt = str(inbound.get("text", ""))
        workspace_raw = inbound.get("workspace")
        if isinstance(workspace_raw, str):
            candidate = (self._default_workspace / workspace_raw).resolve()
            try:
                workspace = validate_workspace_path(candidate, self._default_workspace)
            except ValueError:
                _LOGGER.warning("agent_runner_workspace_escape_rejected raw=%s", workspace_raw)
                workspace = self._default_workspace
        else:
            workspace = self._default_workspace
        _LOGGER.info(
            "agent_runner_inbound_received channel=%s destination=%s workspace=%s prompt_len=%s",
            channel,
            destination,
            workspace,
            len(prompt),
        )
        sender = self._extract_sender(inbound)
        if not self._is_sender_allowed(channel=channel, sender=sender):
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
        if self._rate_limiter is not None:
            if sender and not self._rate_limiter.is_allowed(sender, now=time.monotonic()):
                outbound = {
                    "channel": channel,
                    "destination": destination,
                    "text": "Rate limit exceeded. Try again later.",
                }
                await bus.publish_outbound(outbound)
                _LOGGER.info(
                    "agent_runner_rate_limited channel=%s sender=%s",
                    channel,
                    sender,
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

    def _is_sender_allowed(self, *, channel: str, sender: str | None) -> bool:
        allowed_senders = self._channel_allowed_senders.get(channel)
        if not allowed_senders:
            return True
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
        skipped_keys: list[str] = []
        skipped_complex: list[str] = []
        for key, value in inbound.items():
            key_lower = key.lower()
            if any(token in key_lower for token in self._SENSITIVE_TOKENS):
                skipped_keys.append(key)
                continue
            if isinstance(value, str | int | float | bool) or value is None:
                sanitized[key] = value
            else:
                skipped_complex.append(f"{key}=<{type(value).__name__}>")
        if skipped_keys:
            _LOGGER.debug("metadata_sensitive_keys_dropped keys=%s", skipped_keys)
        if skipped_complex:
            _LOGGER.debug("metadata_complex_values_dropped fields=%s", skipped_complex)
        return sanitized
