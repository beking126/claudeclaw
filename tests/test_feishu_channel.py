import asyncio
import json


class _FakeResponse:
    def __init__(self, ok: bool = True):
        self._ok = ok

    def success(self) -> bool:
        return self._ok


class _FakeMessageApi:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def create(self, request):
        self.calls.append({"receive_id_type": request.receive_id_type, "receive_id": request.receive_id, "content": request.content})
        return _FakeResponse(ok=True)


class _FakeImV1:
    def __init__(self):
        self.message = _FakeMessageApi()


class _FakeIm:
    def __init__(self):
        self.v1 = _FakeImV1()


class _FakeClient:
    def __init__(self):
        self.im = _FakeIm()

    @classmethod
    def builder(cls):
        class _Builder:
            def __init__(self):
                self._app_id = ""
                self._app_secret = ""

            def app_id(self, app_id: str):
                self._app_id = app_id
                return self

            def app_secret(self, app_secret: str):
                self._app_secret = app_secret
                return self

            def log_level(self, _level):
                return self

            def build(self):
                _ = self._app_id
                _ = self._app_secret
                return _FakeClient()

        return _Builder()


class _FakeWsClient:
    def __init__(self, _app_id: str, _app_secret: str, event_handler, log_level):
        _ = log_level
        self.event_handler = event_handler
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FakeWsModule:
    Client = _FakeWsClient


class _FakeEventDispatcherHandler:
    @classmethod
    def builder(cls, _encrypt_key: str, _verification_token: str):
        class _Builder:
            def __init__(self):
                self.handler = None

            def register_p2_im_message_receive_v1(self, handler):
                self.handler = handler
                return self

            def build(self):
                return self.handler

        return _Builder()


class _FakeCreateMessageRequest:
    @classmethod
    def builder(cls):
        class _Builder:
            def __init__(self):
                self._receive_id_type = ""
                self._receive_id = ""
                self._content = ""

            def receive_id_type(self, receive_id_type: str):
                self._receive_id_type = receive_id_type
                return self

            def request_body(self, body):
                self._receive_id = body.receive_id_value
                self._content = body.content_value
                return self

            def build(self):
                self.receive_id_type = self._receive_id_type
                self.receive_id = self._receive_id
                self.content = self._content
                return self

        return _Builder()


class _FakeCreateMessageRequestBody:
    @classmethod
    def builder(cls):
        class _Builder:
            def __init__(self):
                self.receive_id_value = ""
                self.msg_type_value = ""
                self.content_value = ""

            def receive_id(self, receive_id: str):
                self.receive_id_value = receive_id
                return self

            def msg_type(self, msg_type: str):
                self.msg_type_value = msg_type
                return self

            def content(self, content: str):
                self.content_value = content
                return self

            def build(self):
                return self

        return _Builder()


def _fake_feishu_sdk():
    class _LogLevel:
        INFO = "INFO"

    return {
        "Client": _FakeClient,
        "ws": _FakeWsModule,
        "EventDispatcherHandler": _FakeEventDispatcherHandler,
        "CreateMessageRequest": _FakeCreateMessageRequest,
        "CreateMessageRequestBody": _FakeCreateMessageRequestBody,
        "LogLevel": _LogLevel,
    }


class _FakeEventMessage:
    def __init__(self, *, message_id: str, chat_id: str, chat_type: str, message_type: str, content: str):
        self.message_id = message_id
        self.chat_id = chat_id
        self.chat_type = chat_type
        self.message_type = message_type
        self.content = content


class _FakeSenderId:
    def __init__(self, open_id: str):
        self.open_id = open_id


class _FakeSender:
    def __init__(self, open_id: str, sender_type: str = "user"):
        self.sender_id = _FakeSenderId(open_id)
        self.sender_type = sender_type


class _FakeEvent:
    def __init__(self, message: _FakeEventMessage, sender: _FakeSender):
        self.message = message
        self.sender = sender


class _FakeData:
    def __init__(self, event: _FakeEvent):
        self.event = event


def test_feishu_channel_lifecycle_and_health():
    from claudebot_gateway.channels.feishu import FeishuChannel
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
        channel = FeishuChannel(
            bus=MessageBus(),
            app_id="app-1",
            app_secret="secret-1",
            verify_token="verify-1",
            sdk_loader=_fake_feishu_sdk,
        )
        await channel.start()
        await channel.send({"channel": "feishu", "destination": "oc_group_1", "text": "hello group"})
        await channel.send({"channel": "feishu", "destination": "ou_user_1", "text": "hello user"})
        running = channel.health()
        calls = channel._client.im.v1.message.calls if channel._client is not None else []
        await channel.stop()
        stopped = channel.health()
        return running, stopped, calls

    running, stopped, calls = asyncio.run(_run())
    assert running["running"] is True
    assert running["connected"] is True
    assert stopped["running"] is False
    assert calls[0]["receive_id_type"] == "chat_id"
    assert calls[1]["receive_id_type"] == "open_id"


def test_feishu_channel_process_raw_message_normalizes_and_dedups():
    from claudebot_gateway.channels.feishu import FeishuChannel
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> tuple[dict[str, object], int]:
        bus = MessageBus()
        channel = FeishuChannel(bus=bus, app_id="app-1", app_secret="secret-1", sdk_loader=_fake_feishu_sdk)
        await channel.start()
        data = _FakeData(
            _FakeEvent(
                _FakeEventMessage(
                    message_id="m-1",
                    chat_id="oc_group_1",
                    chat_type="group",
                    message_type="text",
                    content=json.dumps({"text": "hello from feishu"}),
                ),
                _FakeSender("ou_xxx", sender_type="user"),
            )
        )
        await channel._on_message(data)
        await channel._on_message(data)
        inbound = await bus.inbound.get()
        seen_event_count = channel.health().get("seen_event_count", 0)
        return inbound, int(seen_event_count) if isinstance(seen_event_count, int | str) else 0

    inbound, seen_count = asyncio.run(_run())
    assert seen_count == 1
    assert inbound["channel"] == "feishu"
    assert inbound["destination"] == "oc_group_1"
    assert inbound["text"] == "hello from feishu"
    assert inbound["sender"] == "ou_xxx"


def test_feishu_channel_send_retries_then_succeeds():
    from claudebot_gateway.channels.feishu import FeishuChannel

    async def _run() -> int:
        class _TestFeishu(FeishuChannel):
            def __init__(self):
                super().__init__(
                    app_id="app-1",
                    app_secret="secret-1",
                    send_max_attempts=3,
                    base_backoff_seconds=0.0,
                    sdk_loader=_fake_feishu_sdk,
                )
                self.attempts = 0

            async def _send_message(self, message: dict[str, str]) -> None:
                _ = message
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("send failed")

        channel = _TestFeishu()
        await channel.start()
        await channel.send({"channel": "feishu", "destination": "chat-1", "text": "hello"})
        return channel.attempts

    attempts = asyncio.run(_run())
    assert attempts == 3
