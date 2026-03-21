from claudebot_gateway.channels.base import BaseChannel


class DiscordChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__()

    async def send(self, message: dict[str, str]) -> None:
        _ = message
