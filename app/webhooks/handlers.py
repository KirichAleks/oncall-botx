import logging
import asyncio
import json
from typing import Dict, Any
from uuid import UUID
from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.routing import ChatRouter
from app.webhooks.formatters import format_oncall_webhook_message

logger = logging.getLogger(__name__)


# Инициализируем маршрутизатор при загрузке модуля
_chat_router: ChatRouter = None

def _initialize_router():
    """Инициализировать маршрутизатор из конфигурации"""
    global _chat_router
    
    routing_config = settings.get_chat_routing()
    fallback_chat_id = settings.target_chat_id  # Для обратной совместимости
    
    _chat_router = ChatRouter(routing_config, fallback_chat_id)
    logger.info(_chat_router.get_routing_summary())

def get_router() -> ChatRouter:
    """Получить инициализированный маршрутизатор"""
    global _chat_router
    if _chat_router is None:
        _initialize_router()
    return _chat_router

async def handle_oncall_webhook(request: Request, bot):
    """Основной обработчик вебхуков от Grafana OnCall с маршрутизацией в разные чаты"""
    try:
        # Читаем сырые данные и парсим JSON
        raw_body = await request.body()
        logger.debug("Raw webhook data: %s", (raw_body.decode(errors="replace")))

        try:
            event_data = json.loads(raw_body.decode() if isinstance(raw_body, (bytes, bytearray)) else raw_body)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON received in webhook: %s", e)
            return JSONResponse(
                status_code=HTTPStatus.BAD_REQUEST,
                content={"status": "error", "detail": "Invalid JSON"},
            )

        if not isinstance(event_data, dict):
            logger.error("Webhook payload is not a JSON object")
            return JSONResponse(
                status_code=HTTPStatus.BAD_REQUEST,
                content={"status": "error", "detail": "Invalid payload"},
            )

        # Валидация основных полей
        if not event_data.get("alert_group"):
            logger.warning("Received event without alert_group")
            return JSONResponse(
                status_code=HTTPStatus.BAD_REQUEST,
                content={"status": "error", "message": "Missing alert_group"},
            )

        event_type = event_data.get("event", {}).get("type", "unknown")
        alert_group_id = event_data.get("alert_group", {}).get("id", "unknown")
        
        # Получаем маршрутизатор и определяем целевой чат
        router = get_router()
        target_chat_id = router.get_chat_id(event_data)
        
        if not target_chat_id:
            logger.error(
                "Cannot determine target chat_id for event. Event: type=%s, alert_group=%s, "
                "integration=%s",
                event_type, alert_group_id, event_data.get("integration", {}).get("name")
            )
            return JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                content={
                    "status": "error",
                    "message": "Cannot determine target chat (no routing configuration or fallback)"
                },
            )
        
        # Проверяем валидность UUID целевого чата
        if not router.validate_chat_id(target_chat_id):
            logger.error("Target chat_id is not a valid UUID: %s", target_chat_id)
            return JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                content={"status": "error", "message": "Invalid target chat_id"},
            )
        
        logger.info(
            "Received %s event for alert group %s from integration=%s -> chat_id=%s",
            event_type, alert_group_id,
            event_data.get("integration", {}).get("name"),
            target_chat_id
        )

        # Асинхронная обработка события в фоне
        asyncio.create_task(process_oncall_event_async(event_data, target_chat_id, bot))

        logger.info("%s event for %s accepted for processing", event_type, alert_group_id)
        return JSONResponse(
            status_code=HTTPStatus.ACCEPTED,
            content={"status": "accepted", "message": "Event is being processed"},
        )

    except Exception as e:
        logger.exception("Error processing Grafana OnCall event: %s", e)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content={"status": "error", "detail": "internal error"},
        )

async def process_oncall_event_async(event_data: dict, target_chat_id: str, bot):
    """Асинхронная обработка события OnCall"""
    try:
        event_type = (event_data.get("event", {}).get("type") or "").lower()
        alert_group_id = event_data.get("alert_group", {}).get("id", "unknown")

        # Убираем прежнюю дедупликацию escalation. Поведение теперь задаётся логикой форматтера по event_type.

        alert_message = parse_oncall_event(event_data)

        if alert_message:
            try:
                await bot.send_message(
                    bot_id=UUID(settings.botx_bot_id),
                    chat_id=UUID(target_chat_id),
                    body=alert_message,
                    wait_callback=settings.botx_wait_callback,
                )
            except Exception:
                logger.exception("Failed to send message to chat %s", target_chat_id)
            logger.info("%s event for %s sent to chat %s", event_type, alert_group_id, target_chat_id)
        else:
            logger.warning("Empty alert message generated, skipping send")

    except Exception as e:
        logger.exception("Error in async processing: %s", e)

def parse_oncall_event(event_data: Dict[str, Any]) -> str:
    """Парсинг события и формирование сообщения (URL берется внутри форматтера)."""
    try:
        return format_oncall_webhook_message(event_data)
    except Exception as e:
        logger.exception("Error parsing OnCall event: %s", e)
        return f"❌ Error processing alert: {str(e)}"