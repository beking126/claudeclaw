import logging

from claudebot_gateway.channels.base import BaseChannel

_LOGGER = logging.getLogger("claudebot_gateway.channels.discord")


class DiscordChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__()

    async def send(self, message: dict[str, str]) -> None:
        _LOGGER.warning("discord_send_stub channel not implemented, message dropped")
