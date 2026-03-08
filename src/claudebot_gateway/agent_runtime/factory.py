from collections.abc import AsyncIterator, Callable
from typing import Any

from claudebot_gateway.agent_runtime.claude_adapter import ClaudeSdkAdapter
from claudebot_gateway.agent_runtime.types import AgentRuntime
from claudebot_gateway.config import GatewayConfig

QueryCallable = Callable[..., AsyncIterator[Any]]


class UnsupportedRuntimeProviderError(ValueError):
    pass


def create_agent_runtime(config: GatewayConfig, query_callable: QueryCallable | None = None) -> AgentRuntime:
    provider = config.agent_runtime.provider.strip().lower()
    if provider == "claude":
        return ClaudeSdkAdapter(options=config.agent_runtime.claude, query_callable=query_callable)
    raise UnsupportedRuntimeProviderError(
        f"Unsupported agent runtime provider '{config.agent_runtime.provider}'. Supported providers: claude."
    )
