from pathlib import Path
from typing import Any

from claudebot_gateway.agent_runtime import AgentExecutionRequest, AgentRuntime
from claudebot_gateway.message_bus import MessageBus


class AgentRunner:
    def __init__(self, *, runtime: AgentRuntime, default_workspace: Path):
        self._runtime = runtime
        self._default_workspace = Path(default_workspace)

    async def process_once(self, bus: MessageBus) -> dict[str, Any]:
        inbound = await bus.inbound.get()
        channel = str(inbound.get("channel", "cli"))
        destination = str(inbound.get("destination", "cli:stdout"))
        prompt = str(inbound.get("text", ""))
        workspace_raw = inbound.get("workspace")
        workspace = Path(workspace_raw) if isinstance(workspace_raw, str) else self._default_workspace
        try:
            result = await self._runtime.execute(
                AgentExecutionRequest(
                    prompt=prompt,
                    workspace=workspace,
                    channel=channel,
                    destination=destination,
                    metadata=inbound,
                )
            )
            text = result.text
        except Exception:
            text = "Agent execution failed. Try again shortly."
        outbound = {
            "channel": channel,
            "destination": destination,
            "text": text,
        }
        await bus.publish_outbound(outbound)
        return outbound
