import asyncio


class _FakeFilter:
    def __or__(self, other):
        _ = other
        return self

    def __and__(self, other):
        _ = other
        return self

    def __invert__(self):
        return self


class _FakeMessage:
    def __init__(self, *, text: str | None = None, caption: str | None = None, chat_id: int = 1, message_id: int = 1):
        self.text = text
        self.caption = caption
        self.chat_id = chat_id
        self.message_id = message_id
        self.photo = None
        self.voice = None
        self.audio = None
        self.document = None

        class _Chat:
            type = "private"

        self.chat = _Chat()
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _FakeUser:
    def __init__(self, *, user_id: int = 100, username: str | None = "tester", first_name: str = "Tester"):
        self.id = user_id
        self.username = username
        self.first_name = first_name


class _FakeUpdate:
    def __init__(self, *, message: _FakeMessage | None, user: _FakeUser | None):
        self.message = message
        self.effective_user = user


class _FakeBot:
    def __init__(self):
        self.sent: list[dict[str, object]] = []

    async def get_me(self):
        class _Me:
            username = "fake_bot"

        return _Me()

    async def send_message(self, *, chat_id: int, text: str, parse_mode: str | None = None) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})


class _FakeUpdater:
    def __init__(self):
        self.running = False

    async def start_polling(self, **kwargs) -> None:
        _ = kwargs
        self.running = True

    async def stop(self) -> None:
        self.running = False


class _FakeApplication:
    def __init__(self):
        self.bot = _FakeBot()
        self.updater = _FakeUpdater()
        self.handlers: list[object] = []

    @classmethod
    def builder(cls):
        class _Builder:
            def __init__(self):
                self._token = ""

            def token(self, token: str):
                self._token = token
                return self

            def build(self):
                _ = self._token
                return _FakeApplication()

        return _Builder()

    def add_handler(self, handler: object) -> None:
        self.handlers.append(handler)

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


def _fake_telegram_sdk():
    class _Filters:
        TEXT = _FakeFilter()
        PHOTO = _FakeFilter()
        VOICE = _FakeFilter()
        AUDIO = _FakeFilter()
        COMMAND = _FakeFilter()

        class Document:
            ALL = _FakeFilter()

    class _MessageHandler:
        def __init__(self, *_args, **_kwargs):
            return None

    class _CommandHandler:
        def __init__(self, *_args, **_kwargs):
            return None

    return {
        "Application": _FakeApplication,
        "MessageHandler": _MessageHandler,
        "CommandHandler": _CommandHandler,
        "filters": _Filters,
    }


def test_telegram_channel_processes_raw_message_inline_to_bus():
    from claudebot_gateway.channels.telegram import TelegramChannel
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> dict[str, object]:
        bus = MessageBus()
        channel = TelegramChannel(bus=bus, token="token-1", sdk_loader=_fake_telegram_sdk)
        await channel.start()
        await channel.process_raw_message(
            {
                "destination": "chat:1",
                "text": "hello from tg",
                "sender": "user-01",
                "metadata": {"message_id": "m1"},
            }
        )
        return await bus.inbound.get()

    inbound = asyncio.run(_run())
    assert inbound["channel"] == "telegram"
    assert inbound["destination"] == "chat:1"
    assert inbound["text"] == "hello from tg"
    assert inbound["sender"] == "user-01"


def test_telegram_channel_send_retries_until_success():
    from claudebot_gateway.channels.telegram import TelegramChannel

    async def _run() -> int:
        class _TestTelegram(TelegramChannel):
            def __init__(self):
                super().__init__(
                    token="token-1",
                    send_max_attempts=3,
                    base_backoff_seconds=0.0,
                    sdk_loader=_fake_telegram_sdk,
                )
                self.attempts = 0

            async def _send_message(self, message: dict[str, str]) -> None:
                _ = message
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("send failed")

        channel = _TestTelegram()
        await channel.start()
        await channel.send({"channel": "telegram", "destination": "chat:1", "text": "hello"})
        return channel.attempts

    attempts = asyncio.run(_run())
    assert attempts == 3


def test_telegram_channel_start_stop_and_send_with_sdk():
    from claudebot_gateway.channels.telegram import TelegramChannel
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> dict[str, object]:
        bus = MessageBus()
        channel = TelegramChannel(bus=bus, token="token-1", sdk_loader=_fake_telegram_sdk)
        await channel.start()
        await channel.send({"channel": "telegram", "destination": "1234", "text": "**hello**"})
        health_running = channel.health()
        await channel.stop()
        health_stopped = channel.health()
        sent = channel._app.bot.sent if channel._app is not None else []
        return {
            "running": health_running,
            "stopped": health_stopped,
            "sent": sent,
        }

    data = asyncio.run(_run())
    assert data["running"]["running"] is True
    assert data["stopped"]["running"] is False
    assert data["sent"][0]["chat_id"] == 1234


def test_telegram_channel_on_message_normalizes_into_bus():
    from claudebot_gateway.channels.telegram import TelegramChannel
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> dict[str, object]:
        bus = MessageBus()
        channel = TelegramChannel(bus=bus, token="token-1", sdk_loader=_fake_telegram_sdk)
        await channel.start()
        update = _FakeUpdate(message=_FakeMessage(text="hello inbound", chat_id=99, message_id=10), user=_FakeUser(user_id=42, username="alice"))
        await channel._on_message(update, None)
        return await bus.inbound.get()

    inbound = asyncio.run(_run())
    assert inbound["channel"] == "telegram"
    assert inbound["destination"] == "99"
    assert inbound["text"] == "hello inbound"
    assert inbound["sender"] == "42|alice"


def test_telegram_health_exposes_polling_state():
    from claudebot_gateway.channels.telegram import TelegramChannel

    async def _run() -> dict[str, object]:
        channel = TelegramChannel(token="token-1", sdk_loader=_fake_telegram_sdk)
        await channel.start()
        health = channel.health()
        await channel.stop()
        return health

    health = asyncio.run(_run())
    assert health["polling_active"] is True
    assert health["reconnect_attempts"] == 0


def test_telegram_poll_once_detects_stopped_polling_and_reconnects():
    from claudebot_gateway.channels.telegram import TelegramChannel

    async def _run() -> dict[str, object]:
        channel = TelegramChannel(token="token-1", sdk_loader=_fake_telegram_sdk)
        await channel.start()
        # Simulate polling stopped by setting running = False on updater
        channel._app.updater.running = False
        await channel.poll_once()
        # After reconnect, the fake updater sets running = True via start_polling
        return channel.health()

    health = asyncio.run(_run())
    assert health["polling_active"] is True
    assert health["reconnect_attempts"] == 0


def test_telegram_poll_once_noop_when_polling_active():
    from claudebot_gateway.channels.telegram import TelegramChannel

    async def _run() -> int:
        channel = TelegramChannel(token="token-1", sdk_loader=_fake_telegram_sdk)
        await channel.start()
        assert channel._app.updater.running is True
        await channel.poll_once()
        await channel.stop()
        return channel._reconnect_attempts

    attempts = asyncio.run(_run())
    assert attempts == 0
