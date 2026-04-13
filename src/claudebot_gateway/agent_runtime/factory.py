from claudebot_gateway.agent_runtime.claude_adapter import ClaudeSdkAdapter, QueryCallable
from claudebot_gateway.agent_runtime.openai_adapter import OpenAIAdapter, OpenAIRuntimeOptions
from claudebot_gateway.agent_runtime.types import AgentRuntime
from claudebot_gateway.config import GatewayConfig


class UnsupportedRuntimeProviderError(ValueError):
    pass


def create_agent_runtime(config: GatewayConfig, query_callable: QueryCallable | None = None) -> AgentRuntime:
    provider = config.agent_runtime.provider.strip().lower()
    if provider == "claude":
        return ClaudeSdkAdapter(options=config.agent_runtime.claude, query_callable=query_callable)
    if provider == "openai":
        claude_opts = config.agent_runtime.claude
        openai_options = OpenAIRuntimeOptions(
            model=claude_opts.model or "gpt-4o",
            system_prompt=claude_opts.system_prompt,
        )
        return OpenAIAdapter(options=openai_options)
    raise UnsupportedRuntimeProviderError(
        f"Unsupported agent runtime provider '{config.agent_runtime.provider}'. Supported providers: claude, openai."
    )
