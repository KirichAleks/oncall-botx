"""
Вспомогательные функции для отправки сообщений боту в конкретные чаты.
"""
import logging
from typing import Optional
from uuid import UUID

from pybotx import Bot
from pydantic import ValidationError
from app.config import settings

logger = logging.getLogger(__name__)


async def send_message_to_chat(
    bot: Bot,
    chat_id: str,
    text: str,
) -> bool:
    """
    Отправить сообщение в конкретный чат.
    
    Args:
        bot: Экземпляр Bot из pybotx
        chat_id: UUID чата в виде строки
        text: Текст сообщения
        
    Returns:
        True если сообщение отправлено, False если ошибка
    """
    try:
        # Валидируем chat_id как UUID
        try:
            UUID(chat_id)
        except (ValueError, ValidationError):
            logger.error("Invalid chat_id format (not a UUID): %s", chat_id)
            return False
        
        # Отправляем сообщение через bot.send_message или bot.answer_message
        # В зависимости от версии pybotx нужно использовать нужный метод
        if hasattr(bot, "send_message") and callable(getattr(bot, "send_message")):
            # Bot.send_message требует bot_id и chat_id (UUID). Передаём bot_id из настроек.
            try:
                bot_uuid = UUID(settings.botx_bot_id)
            except Exception:
                logger.exception("Invalid BOTX_BOT_ID in settings: %s", settings.botx_bot_id)
                return False

            try:
                chat_uuid = UUID(chat_id)
            except Exception:
                logger.exception("Invalid chat_id format when sending message: %s", chat_id)
                return False

            # Log the outgoing message content at DEBUG level (may contain PII)
            logger.debug("Sending message to chat. bot_id=%s chat_id=%s body=%s", bot_uuid, chat_uuid, text)

            # Call pybotx and log returned sync_id to trace delivery
            sync_id = await bot.send_message(
                bot_id=bot_uuid,
                chat_id=chat_uuid,
                body=text,
                wait_callback=settings.botx_wait_callback,
            )
            logger.info("bot.send_message returned sync_id=%s for chat=%s", sync_id, chat_uuid)
        elif hasattr(bot, "answer_message") and callable(getattr(bot, "answer_message")):
            # answer_message требует контекст сообщения, не подходит для отправки в произвольный чат
            logger.error("bot.answer_message requires message context, cannot send to arbitrary chat")
            return False
        else:
            logger.error("Bot has no send_message or answer_message method")
            return False
        
        logger.info("Message sent to chat %s", chat_id)
        return True
    except Exception:
        logger.exception("Error sending message to chat %s", chat_id)
        return False


async def send_formatted_oncall_to_chat(
    bot: Bot,
    chat_id: str,
    schedule_name: str,
    shift_data: dict,
) -> bool:
    """
    Отправить отформатированную информацию о дежурном в чат.
    
    Args:
        bot: Экземпляр Bot
        chat_id: UUID чата
        schedule_name: Имя расписания
        shift_data: Данные о смене
        
    Returns:
        True если отправлено, False если ошибка
    """
    try:
        from app.webhooks.schedule_formatters import format_current_oncall
        
        text = format_current_oncall(shift_data, schedule_name)
        return await send_message_to_chat(bot, chat_id, text)
    except Exception:
        logger.exception("Error sending formatted oncall to chat %s", chat_id)
        return False
