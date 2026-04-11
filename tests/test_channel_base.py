import asyncio


def test_base_channel_provides_default_lifecycle():
    from claudebot_gateway.channels.base import BaseChannel

    class _OnlySendChannel(BaseChannel):
        async def send(self, message: dict[str, str]) -> None:
            _ = message

    async def _run() -> dict[str, object]:
        channel = _OnlySendChannel()
        await channel.start()
        running = channel.health()
        await channel.poll_once()
        await channel.stop()
        stopped = channel.health()
        return {"running_state": running["running"], "stopped_state": stopped["running"]}

    health = asyncio.run(_run())
    assert health["running_state"] is True
    assert health["stopped_state"] is False


def test_concrete_channels_implement_base_channel():
    from claudebot_gateway.channels.base import BaseChannel
    from claudebot_gateway.channels.cli import CliChannel
    from claudebot_gateway.channels.discord import DiscordChannel
    from claudebot_gateway.channels.feishu import FeishuChannel
    from claudebot_gateway.channels.slack import SlackBridgeChannel
    from claudebot_gateway.channels.telegram import TelegramChannel
    from claudebot_gateway.channels.whatsapp import WhatsAppBridgeChannel

    instances = [
        CliChannel(),
        TelegramChannel(),
        DiscordChannel(),
        FeishuChannel(),
        WhatsAppBridgeChannel(),
        SlackBridgeChannel(),
    ]
    assert all(isinstance(channel, BaseChannel) for channel in instances)


def test_cli_channel_send_prints_text_to_stdout(capsys):
    from claudebot_gateway.channels.cli import CliChannel

    async def _run() -> None:
        channel = CliChannel()
        await channel.send({"channel": "cli", "destination": "cli:stdout", "text": "hello world"})

    asyncio.run(_run())
    captured = capsys.readouterr()
    assert "hello world" in captured.out


def test_cli_channel_send_empty_text_does_not_crash(capsys):
    from claudebot_gateway.channels.cli import CliChannel

    async def _run() -> None:
        channel = CliChannel()
        await channel.send({"channel": "cli", "destination": "cli:stdout", "text": ""})

    asyncio.run(_run())
    captured = capsys.readouterr()
    assert captured.out == ""
