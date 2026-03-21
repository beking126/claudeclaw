import asyncio
import importlib
import logging
import os
import re
from collections.abc import Callable
from typing import Any

from claudebot_gateway.channels.base import BaseChannel
from claudebot_gateway.message_bus import MessageBus


_LOGGER = logging.getLogger("claudebot_gateway.channels.telegram")


class TelegramChannel(BaseChannel):
    def __init__(
        self,
        *,
        bus: MessageBus | None = None,
        token: str | None = None,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 8.0,
        send_max_attempts: int = 3,
        sdk_loader: Callable[[], dict[str, Any]] | None = None,
    ):
        super().__init__()
        self._bus = bus
        self._token = token or os.getenv("CLAUDEBOT_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        self._base_backoff_seconds = max(0.0, base_backoff_seconds)
        self._max_backoff_seconds = max(self._base_backoff_seconds, max_backoff_seconds)
        self._send_max_attempts = max(1, send_max_attempts)
        self._sdk_loader = sdk_loader or self._load_sdk
        self._running = False
        self._last_error: str | None = None
        self._reconnect_attempts = 0
        self._app: Any = None
        self._chat_ids: dict[str, int] = {}

    async def start(self) -> None:
        if self._running:
            return
        if not self._token:
            raise RuntimeError("telegram bot token is not configured")
        sdk = self._sdk_loader()
        application_cls = sdk["Application"]
        message_handler_cls = sdk["MessageHandler"]
        command_handler_cls = sdk["CommandHandler"]
        sdk_filters = sdk["filters"]
        self._app = application_cls.builder().token(self._token).build()
        self._app.add_handler(
            message_handler_cls(
                (sdk_filters.TEXT | sdk_filters.PHOTO | sdk_filters.VOICE | sdk_filters.AUDIO | sdk_filters.Document.ALL)
                & ~sdk_filters.COMMAND,
                self._on_message,
            )
        )
        self._app.add_handler(command_handler_cls("start", self._on_start))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(allowed_updates=["message"], drop_pending_updates=True)
        try:
            bot_info = await self._app.bot.get_me()
            username = getattr(bot_info, "username", "unknown")
            _LOGGER.info("telegram_connected username=%s", username)
        except Exception:
            _LOGGER.info("telegram_connected username=unknown")
        self._running = True
        self._last_error = None

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._app is not None:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def process_raw_message(self, raw_message: dict[str, Any]) -> None:
        if not self._running:
            raise RuntimeError("telegram channel is not running")
        if self._bus is None:
            raise RuntimeError("telegram channel has no message bus")
        inbound: dict[str, Any] = {
            "channel": "telegram",
            "destination": str(raw_message.get("destination", "")),
            "text": str(raw_message.get("text", "")),
        }
        sender = raw_message.get("sender")
        if isinstance(sender, str) and sender:
            inbound["sender"] = sender
        metadata = raw_message.get("metadata")
        if isinstance(metadata, dict):
            safe_metadata = {k: v for k, v in metadata.items() if isinstance(k, str) and isinstance(v, str | int | float | bool)}
            if safe_metadata:
                inbound["metadata"] = safe_metadata
        await self._bus.publish_inbound(inbound)
        self._last_error = None

    async def send(self, message: dict[str, str]) -> None:
        if not self._running:
            raise RuntimeError("telegram channel is not running")
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
                    "telegram_send_retry attempt=%s retry_in=%s error=%s",
                    attempt,
                    f"{backoff:.2f}s",
                    self._last_error,
                )
                if backoff > 0:
                    await asyncio.sleep(backoff)
        if last_exception is None:
            raise RuntimeError("telegram send failed without exception")
        raise last_exception

    def health(self) -> dict[str, object]:
        return {
            "running": self._running,
            "last_error": self._last_error,
            "reconnect_attempts": self._reconnect_attempts,
            "connected": self._app is not None,
        }

    def _next_backoff_seconds(self, attempt: int) -> float:
        delay = self._base_backoff_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self._max_backoff_seconds)

    async def _send_message(self, message: dict[str, str]) -> None:
        if self._app is None:
            raise RuntimeError("telegram app is not initialized")
        destination = message.get("destination", "")
        chat_id = int(destination)
        text = message.get("text", "")
        html = self._markdown_to_telegram_html(text)
        try:
            await self._app.bot.send_message(chat_id=chat_id, text=html, parse_mode="HTML")
        except Exception:
            await self._app.bot.send_message(chat_id=chat_id, text=text)

    async def _on_start(self, update: Any, context: Any) -> None:
        _ = context
        message = getattr(update, "message", None)
        user = getattr(update, "effective_user", None)
        if message is None or user is None:
            return
        first_name = getattr(user, "first_name", "there")
        await message.reply_text(f"👋 Hi {first_name}! I'm claudebot gateway.")

    async def _on_message(self, update: Any, context: Any) -> None:
        _ = context
        message = getattr(update, "message", None)
        user = getattr(update, "effective_user", None)
        if message is None or user is None:
            return
        sender = str(getattr(user, "id", "unknown"))
        username = getattr(user, "username", None)
        if isinstance(username, str) and username:
            sender = f"{sender}|{username}"
        chat_id = str(getattr(message, "chat_id", ""))
        self._chat_ids[sender] = int(chat_id) if chat_id.isdigit() else 0
        text = getattr(message, "text", None) or getattr(message, "caption", None) or "[empty message]"
        metadata = {
            "message_id": getattr(message, "message_id", 0),
            "username": getattr(user, "username", ""),
            "first_name": getattr(user, "first_name", ""),
        }
        await self.process_raw_message(
            {
                "destination": chat_id,
                "text": text,
                "sender": sender,
                "metadata": metadata,
            }
        )

    def _load_sdk(self) -> dict[str, Any]:
        try:
            ext_module = importlib.import_module("telegram.ext")
        except Exception as exc:
            raise RuntimeError("python-telegram-bot is required for TelegramChannel") from exc
        application = getattr(ext_module, "Application")
        message_handler = getattr(ext_module, "MessageHandler")
        command_handler = getattr(ext_module, "CommandHandler")
        filters = getattr(ext_module, "filters")
        return {
            "Application": application,
            "MessageHandler": message_handler,
            "CommandHandler": command_handler,
            "filters": filters,
        }

    def _markdown_to_telegram_html(self, text: str) -> str:
        if not text:
            return ""
        code_blocks: list[str] = []

        def _save_code_block(match: re.Match[str]) -> str:
            code_blocks.append(match.group(1))
            return f"\x00CB{len(code_blocks) - 1}\x00"

        text = re.sub(r"```[\w]*\n?([\s\S]*?)```", _save_code_block, text)
        inline_codes: list[str] = []

        def _save_inline_code(match: re.Match[str]) -> str:
            inline_codes.append(match.group(1))
            return f"\x00IC{len(inline_codes) - 1}\x00"

        text = re.sub(r"`([^`]+)`", _save_inline_code, text)
        text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)
        text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
        text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)
        text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
        text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)
        for index, code in enumerate(inline_codes):
            escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace(f"\x00IC{index}\x00", f"<code>{escaped}</code>")
        for index, code in enumerate(code_blocks):
            escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace(f"\x00CB{index}\x00", f"<pre><code>{escaped}</code></pre>")
        return text
