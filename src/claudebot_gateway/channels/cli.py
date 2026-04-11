import logging
import sys

from claudebot_gateway.channels.base import BaseChannel

_LOGGER = logging.getLogger("claudebot_gateway.channels.cli")


class CliChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__()

    async def send(self, message: dict[str, str]) -> None:
        text = message.get("text", "")
        if text:
            sys.stdout.write(text + "\n")
            sys.stdout.flush()
        _LOGGER.info("cli_channel_sent text_len=%s", len(text))
