class CliChannel:
    async def poll_once(self) -> bool:
        return True

    async def send(self, message: dict[str, str]) -> None:
        _ = message
