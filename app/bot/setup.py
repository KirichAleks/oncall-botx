import os
import logging
from uuid import UUID
from typing import Any
from pybotx import Bot, BotAccountWithSecret
from app.config import settings
from app.bot.commands import collector

logger = logging.getLogger(__name__)


class BotWrapper:
    """Light wrapper around pybotx.Bot to provide a stable public API used by the app."""

    def __init__(self, bot: Bot):
        self._bot = bot

    def __getattr__(self, name: str) -> Any:
        # Делегируем все незаданные атрибуты/методы оригинальному боту
        return getattr(self._bot, name)

    async def raw_get_status(self, *args, **kwargs):
        # Попытка вызвать публичный метод raw_get_status без падений
        func = getattr(self._bot, "raw_get_status", None)
        if not callable(func):
            logger.debug("Bot has no raw_get_status method")
            return {"status": "unknown"}
        return await func(*args, **kwargs)

    async def is_ready(self) -> bool:
        """Простейшая проверка готовности бота для health-check"""
        try:
            status = await self.raw_get_status({}, request_headers={})
            if isinstance(status, dict):
                state = status.get("status") or status.get("state") or status.get("result")
                if state and str(state).lower() in {"ready", "ok", "running", "started"}:
                    return True
                if status.get("ok") is True:
                    return True
            return False
        except Exception:
            logger.exception("Failed to get bot readiness")
            return False
def create_bot():
    """Создание и настройка бота"""
    # Парсим UUID бота с понятной ошибкой
    try:
        bot_id = UUID(settings.botx_bot_id)
    except Exception as e:
        logger.exception("Invalid BOTX_BOT_ID")
        raise ValueError(f"Invalid BOTX_BOT_ID: {e}")

    ca_path = "/app/certs/ca.crt"
    account_kwargs = {
        "id": bot_id,
        "host": settings.botx_host,
        "secret_key": settings.botx_secret_key,
        "cts_url": settings.botx_host,
    }

    if os.path.exists(ca_path):
        account_kwargs["ca_certs"] = ca_path
    else:
        logger.warning("CA cert not found at %s, continuing without ca_certs", ca_path)

    bot_account = BotAccountWithSecret(**account_kwargs)

    bot = Bot(collectors=[collector], bot_accounts=[bot_account])
    return BotWrapper(bot)