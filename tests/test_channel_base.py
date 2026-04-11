import asyncio
import logging


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


def test_stub_channels_log_warning_on_send(caplog):
    from claudebot_gateway.channels.discord import DiscordChannel
    from claudebot_gateway.channels.slack import SlackBridgeChannel
    from claudebot_gateway.channels.whatsapp import WhatsAppBridgeChannel

    async def _run() -> None:
        for cls in (DiscordChannel, SlackBridgeChannel, WhatsAppBridgeChannel):
            channel = cls()
            await channel.send({"channel": "stub", "destination": "x", "text": "hello"})

    caplog.set_level(logging.WARNING)
    asyncio.run(_run())
    messages = [record.getMessage() for record in caplog.records]
    assert any("discord_send_stub" in m for m in messages)
    assert any("slack_send_stub" in m for m in messages)
    assert any("whatsapp_send_stub" in m for m in messages)
