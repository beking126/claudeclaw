import asyncio
import importlib
import json
import logging
import threading
from collections import OrderedDict
from typing import Any

from claudebot_gateway.message_bus import MessageBus


_LOGGER = logging.getLogger("claudebot_gateway.channels.feishu")


class FeishuChannel:
    def __init__(
        self,
        *,
        bus: MessageBus | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
        verify_token: str | None = None,
        encrypt_key: str | None = None,
        send_max_attempts: int = 3,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 8.0,
        sdk_loader: Any = None,
    ):
        self._bus = bus
        self._app_id = app_id
        self._app_secret = app_secret
        self._verify_token = verify_token
        self._encrypt_key = encrypt_key
        self._send_max_attempts = max(1, send_max_attempts)
        self._base_backoff_seconds = max(0.0, base_backoff_seconds)
        self._max_backoff_seconds = max(self._base_backoff_seconds, max_backoff_seconds)
        self._sdk_loader = sdk_loader or self._load_sdk
        self._running = False
        self._last_error: str | None = None
        self._reconnect_attempts = 0
        self._seen_event_ids: set[str] = set()
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        if self._running:
            return
        if not self._app_id or not self._app_secret:
            raise RuntimeError("feishu app_id and app_secret are required")
        sdk = self._sdk_loader()
        client_cls = sdk["Client"]
        ws_module = sdk["ws"]
        event_dispatcher_handler_cls = sdk["EventDispatcherHandler"]
        log_level = sdk["LogLevel"]
        self._loop = asyncio.get_running_loop()
        self._client = client_cls.builder().app_id(self._app_id).app_secret(self._app_secret).log_level(log_level.INFO).build()
        event_handler = (
            event_dispatcher_handler_cls.builder(self._encrypt_key or "", self._verify_token or "")
            .register_p2_im_message_receive_v1(self._on_message_sync)
            .build()
        )
        self._ws_client = ws_module.Client(
            self._app_id,
            self._app_secret,
            event_handler=event_handler,
            log_level=log_level.INFO,
        )

        def _run_ws() -> None:
            try:
                if self._ws_client is not None:
                    self._ws_client.start()
            except Exception as exc:
                self._last_error = str(exc)
                _LOGGER.error("feishu_ws_error error=%s", self._last_error)

        self._ws_thread = threading.Thread(target=_run_ws, daemon=True)
        self._ws_thread.start()
        self._running = True
        self._last_error = None

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception as exc:
                self._last_error = str(exc)
                _LOGGER.warning("feishu_ws_stop_failed error=%s", self._last_error)

    async def handle_event(self, payload: dict[str, Any], signature: str | None = None) -> bool:
        if not self._running:
            raise RuntimeError("feishu channel is not running")
        if not self._verify_signature(signature):
            self._last_error = "invalid signature"
            return False
        event_id_raw = payload.get("event_id")
        event_id = str(event_id_raw) if isinstance(event_id_raw, str | int) else ""
        if event_id and event_id in self._seen_event_ids:
            return False
        if event_id:
            self._seen_event_ids.add(event_id)
        await self.process_raw_message(payload)
        return True

    async def process_raw_message(self, raw_message: dict[str, Any]) -> None:
        if not self._running:
            raise RuntimeError("feishu channel is not running")
        if self._bus is None:
            raise RuntimeError("feishu channel has no message bus")
        message_raw = raw_message.get("message")
        sender_raw = raw_message.get("sender")
        destination = ""
        text = ""
        sender = ""
        if isinstance(message_raw, dict):
            destination_raw = message_raw.get("chat_id")
            destination = str(destination_raw) if isinstance(destination_raw, str | int) else ""
            text_raw = message_raw.get("text")
            text = str(text_raw) if isinstance(text_raw, str | int) else ""
        if isinstance(sender_raw, dict):
            sender_id = sender_raw.get("sender_id")
            if isinstance(sender_id, dict):
                open_id = sender_id.get("open_id")
                sender = str(open_id) if isinstance(open_id, str | int) else ""
        inbound: dict[str, Any] = {"channel": "feishu", "destination": destination, "text": text}
        if sender:
            inbound["sender"] = sender
        event_id_raw = raw_message.get("event_id")
        if isinstance(event_id_raw, str):
            inbound["metadata"] = {"event_id": event_id_raw}
        await self._bus.publish_inbound(inbound)
        self._last_error = None

    async def send(self, message: dict[str, str]) -> None:
        if not self._running:
            raise RuntimeError("feishu channel is not running")
        last_exception: Exception | None = None
        for attempt in range(1, self._send_max_attempts + 1):
            try:
                await self._send_message(message)
                self._last_error = None
                return
            except Exception as exc:
                last_exception = exc
                self._last_error = str(exc)
                if attempt == self._send_max_attempts:
                    break
                backoff = self._next_backoff_seconds(attempt)
                _LOGGER.warning(
                    "feishu_send_retry attempt=%s retry_in=%s error=%s",
                    attempt,
                    f"{backoff:.2f}s",
                    self._last_error,
                )
                if backoff > 0:
                    await asyncio.sleep(backoff)
        self._reconnect_attempts += 1
        if last_exception is None:
            raise RuntimeError("feishu send failed without exception")
        raise last_exception

    def health(self) -> dict[str, object]:
        return {
            "running": self._running,
            "last_error": self._last_error,
            "reconnect_attempts": self._reconnect_attempts,
            "seen_event_count": len(self._seen_event_ids),
            "connected": self._client is not None and self._ws_client is not None,
        }

    def _on_message_sync(self, data: Any) -> None:
        if self._loop is None:
            return
        if not self._loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)

    async def _on_message(self, data: Any) -> None:
        if not self._running:
            return
        if self._bus is None:
            return
        event = getattr(data, "event", None)
        message = getattr(event, "message", None)
        sender = getattr(event, "sender", None)
        if message is None or sender is None:
            return
        message_id = getattr(message, "message_id", "")
        if isinstance(message_id, str) and message_id:
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)
            self._seen_event_ids.add(message_id)
        sender_type = getattr(sender, "sender_type", "")
        if sender_type == "bot":
            return
        sender_id = "unknown"
        sender_id_obj = getattr(sender, "sender_id", None)
        if sender_id_obj is not None:
            open_id = getattr(sender_id_obj, "open_id", None)
            if isinstance(open_id, str) and open_id:
                sender_id = open_id
        chat_id = getattr(message, "chat_id", "")
        chat_type = getattr(message, "chat_type", "")
        message_type = getattr(message, "message_type", "")
        raw_content = getattr(message, "content", "")
        content = ""
        if message_type == "text":
            if isinstance(raw_content, str):
                try:
                    parsed = json.loads(raw_content)
                except json.JSONDecodeError:
                    parsed = raw_content
                if isinstance(parsed, dict):
                    text_value = parsed.get("text", "")
                    content = str(text_value) if isinstance(text_value, str | int | float | bool) else ""
                else:
                    content = str(parsed)
        else:
            content = {
                "image": "[image]",
                "audio": "[audio]",
                "file": "[file]",
                "sticker": "[sticker]",
            }.get(message_type, f"[{message_type}]")
        if not content:
            return
        destination = chat_id if chat_type == "group" else sender_id
        await self._bus.publish_inbound(
            {
                "channel": "feishu",
                "destination": str(destination),
                "text": content,
                "sender": sender_id,
                "metadata": {
                    "message_id": str(message_id),
                    "chat_type": str(chat_type),
                    "msg_type": str(message_type),
                },
            }
        )
        self._last_error = None

    def _verify_signature(self, signature: str | None) -> bool:
        if self._verify_token is None:
            return True
        return signature == "ok" or signature == self._verify_token

    def _next_backoff_seconds(self, attempt: int) -> float:
        delay = self._base_backoff_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self._max_backoff_seconds)

    async def _send_message(self, message: dict[str, str]) -> None:
        if self._client is None:
            raise RuntimeError("feishu client not initialized")
        sdk = self._sdk_loader()
        create_message_request_cls = sdk["CreateMessageRequest"]
        create_message_request_body_cls = sdk["CreateMessageRequestBody"]
        destination = message.get("destination", "")
        receive_id_type = "chat_id" if destination.startswith("oc_") else "open_id"
        content = json.dumps({"text": message.get("text", "")})
        request = (
            create_message_request_cls.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                create_message_request_body_cls.builder()
                .receive_id(destination)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError("feishu send failed")

    def _load_sdk(self) -> dict[str, Any]:
        try:
            lark_module = importlib.import_module("lark_oapi")
            im_module = importlib.import_module("lark_oapi.api.im.v1")
        except Exception as exc:
            raise RuntimeError("lark-oapi is required for FeishuChannel") from exc
        return {
            "Client": getattr(lark_module, "Client"),
            "ws": getattr(lark_module, "ws"),
            "EventDispatcherHandler": getattr(lark_module, "EventDispatcherHandler"),
            "CreateMessageRequest": getattr(im_module, "CreateMessageRequest"),
            "CreateMessageRequestBody": getattr(im_module, "CreateMessageRequestBody"),
            "LogLevel": getattr(lark_module, "LogLevel"),
        }
