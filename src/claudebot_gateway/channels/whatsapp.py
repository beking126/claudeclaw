import logging

from claudebot_gateway.channels.base import BaseChannel

_LOGGER = logging.getLogger("claudebot_gateway.channels.whatsapp")


class WhatsAppBridgeChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__()

    async def send(self, message: dict[str, str]) -> None:
        _LOGGER.warning("whatsapp_send_stub channel not implemented, message dropped")
