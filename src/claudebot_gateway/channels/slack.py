import logging

from claudebot_gateway.channels.base import BaseChannel

_LOGGER = logging.getLogger("claudebot_gateway.channels.slack")


class SlackBridgeChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__()

    async def send(self, message: dict[str, str]) -> None:
        _LOGGER.warning("slack_send_stub channel not implemented, message dropped")
