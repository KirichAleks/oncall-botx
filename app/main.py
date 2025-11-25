import logging
from http import HTTPStatus
from datetime import datetime
import asyncio
import inspect
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pybotx import build_command_accepted_response

from app.config import settings
from app.bot.setup import create_bot
from app.bot.helpers import send_message_to_chat, send_formatted_oncall_to_chat
from app.webhooks.handlers import handle_oncall_webhook
from app.grafana.scheduler import fetch_current_oncall, fetch_schedule_info, fetch_all_schedules
from app.webhooks.schedule_formatters import format_current_oncall, format_oncall_list, format_oncall_day_summary
from app.models.routing import ChatRouter

# Настройка логирования
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Инициализация FastAPI
app = FastAPI(
    title="Grafana OnCall Bot",
    version="1.0.0",
    description="Bot for Grafana OnCall notifications via Express"
)

# Инициализация бота
bot = create_bot()

# Инициализация маршрутизатора чатов
chat_router = ChatRouter(
    routing_config=settings.get_chat_routing(),
    fallback_chat_id=settings.target_chat_id
)

# Startup / Shutdown
@app.on_event("startup")
async def on_startup():
    logger.info("Starting Grafana OnCall Bot...")
    try:
        if hasattr(bot, "startup") and callable(getattr(bot, "startup")):
            await bot.startup()
        logger.info("Bot started successfully")
    except Exception:
        logger.exception("Bot startup failed")
        raise

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down Grafana OnCall Bot...")
    try:
        if hasattr(bot, "shutdown") and callable(getattr(bot, "shutdown")):
            await bot.shutdown()
    except Exception:
        logger.exception("Bot shutdown failed")

# Обработка вебхуков от Grafana OnCall
@app.post("/oncall/webhook")
async def webhook_handler(request: Request):
    return await handle_oncall_webhook(request, bot)

# BotX API endpoints
@app.post("/command")
async def command_handler(request: Request) -> JSONResponse:
    """Конечная точка для получения команд от Express/BotX."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    # логируем приходящий запрос (безопасно: не печатаем длинные секреты)
    headers = dict(request.headers)
    logger.info("Incoming /command payload: %s", {k: v for k, v in (payload.items() if isinstance(payload, dict) else [])})
    logger.debug("Incoming /command headers: %s", {"Authorization": headers.get("authorization", "<hidden>")})

    # Попытка передать полезную нагрузку боту; пробуем передавать request_headers если функция поддерживает
    handler_names = ("process_command", "handle_command", "async_execute_raw_bot_command", "handle_raw_command", "process")
    for name in handler_names:
        func = getattr(bot, name, None)
        if callable(func):
            try:
                # пытаемся вызвать с request_headers kw, иначе без
                try:
                    res = func(payload, request_headers=headers)
                except TypeError:
                    res = func(payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                logger.exception("Error while delegating command to bot: %s", name)
            break

    return JSONResponse(status_code=HTTPStatus.ACCEPTED, content=build_command_accepted_response())

@app.post("/notification/callback")
async def callback_handler(request: Request) -> JSONResponse:
    """Callback для асинхронных операций от BotX/Express"""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=HTTPStatus.BAD_REQUEST, content={"status": "error", "detail": "invalid json"})

    setter = getattr(bot, "set_raw_botx_method_result", None) or getattr(bot, "set_method_result", None)
    if callable(setter):
        try:
            res = setter(payload)
            if res and getattr(res, "__await__", None):
                await res
        except Exception:
            logger.exception("Failed to set method result from callback")
            return JSONResponse(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, content={"status": "error"})
    return JSONResponse(status_code=HTTPStatus.OK, content={"status": "ok"})

@app.get("/status")
async def http_status(request: Request) -> JSONResponse:
    """Статус бота для Express"""
    try:
        status = None
        # Передаём заголовок авторизации, чтобы pybotx не выдал UnverifiedRequestError
        auth_headers = {"Authorization": settings.botx_secret_key} if getattr(settings, "botx_secret_key", None) else {}
        if hasattr(bot, "raw_get_status") and callable(getattr(bot, "raw_get_status")):
            try:
                status = await bot.raw_get_status({}, request_headers=auth_headers)
            except Exception:
                logger.exception("raw_get_status failed")
                status = {"status": "unknown"}
        else:
            status = {"status": "unknown"}
        return JSONResponse(status_code=HTTPStatus.OK, content={"status": "ok", "bot_status": status})
    except Exception:
        logger.exception("Status endpoint failed")
        return JSONResponse(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, content={"status": "error"})

@app.get("/health")
async def health_check():
    """Health check для Kubernetes/Docker"""
    try:
        is_ready = False
        auth_headers = {"Authorization": settings.botx_secret_key} if getattr(settings, "botx_secret_key", None) else {}

        if hasattr(bot, "is_ready") and callable(getattr(bot, "is_ready")):
            try:
                is_ready = await bot.is_ready()
            except Exception:
                logger.exception("is_ready check failed")
                is_ready = False
        else:
            if hasattr(bot, "raw_get_status") and callable(getattr(bot, "raw_get_status")):
                try:
                    status = await bot.raw_get_status({}, request_headers=auth_headers)
                    if isinstance(status, dict):
                        bot_state = status.get("status") or status.get("state") or status.get("result")
                        ok_states = {"ready", "ok", "running", "started"}
                        is_ready = (bot_state and str(bot_state).lower() in ok_states) or (status.get("ok") is True)
                    else:
                        is_ready = False
                except Exception:
                    logger.exception("raw_get_status check failed")
                    is_ready = False
            else:
                is_ready = False

        if is_ready:
            return JSONResponse({"status": "healthy", "service": "grafana-oncall-bot", "timestamp": datetime.utcnow().isoformat()})
        else:
            return JSONResponse(status_code=HTTPStatus.SERVICE_UNAVAILABLE, content={"status": "unhealthy", "detail": "bot not ready"})
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse(status_code=HTTPStatus.SERVICE_UNAVAILABLE, content={"status": "unhealthy", "detail": "internal error"})


# ============================================================================
# Scheduler API endpoints — для получения информации о дежурных
# ============================================================================

@app.get("/api/oncall/current")
async def get_current_oncall_http(
    schedule_id: str, 
    send_to_chat: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> JSONResponse:
    """
    GET /api/oncall/current?schedule_id=SBRN8FTNETDZD&send_to_chat=true&start_date=2025-11-11&end_date=2025-11-14
    
    Получить информацию о текущем дежурном и (опционально) отправить в чат.
    
    Args:
        schedule_id: ID расписания в Grafana OnCall
        send_to_chat: Отправить сообщение в чат команды (по team_id)?
        start_date: Начальная дата в формате YYYY-MM-DD (опционально)
        end_date: Конечная дата в формате YYYY-MM-DD (опционально)
        
    Returns:
        JSON с результатом и информацией о дежурном
    """
    try:
        if not schedule_id:
            return JSONResponse(
                status_code=HTTPStatus.BAD_REQUEST,
                content={"status": "error", "detail": "schedule_id is required"}
            )
        
        # Получаем информацию о расписании
        schedule_info = await fetch_schedule_info(schedule_id)
        schedule_name = schedule_info.get("name", "Unknown")
        team_id = schedule_info.get("team_id")
        
        # Получаем дежурных
        shift_data = await fetch_current_oncall(schedule_id, start_date, end_date)
        
        # Нормализуем ответ
        shifts = []
        if isinstance(shift_data, dict):
            if "results" in shift_data and isinstance(shift_data["results"], list):
                shifts = shift_data["results"]
            elif "shifts" in shift_data:
                shifts = shift_data.get("shifts", [])
        elif isinstance(shift_data, list):
            shifts = shift_data
        
        if not shifts:
            return JSONResponse(
                status_code=HTTPStatus.NOT_FOUND,
                content={"status": "error", "detail": f"No shifts found for schedule {schedule_id}"}
            )
        
        shift = shifts[0]
        
        sent_flag = False
        # Отправляем в чат если нужно
        if send_to_chat:
            event_data = {"team_id": team_id} if team_id else {}
            target_chat_id = chat_router.get_chat_id(event_data)

            if target_chat_id:
                try:
                    if len(shifts) > 1:
                        # Если несколько смен — отправляем краткое резюме дня по формату
                        text = format_oncall_day_summary(shifts)
                        sent_flag = await send_message_to_chat(bot, target_chat_id, text)
                        logger.info("Sent oncall list to chat %s for schedule %s", target_chat_id, schedule_id)
                    else:
                        sent_flag = await send_formatted_oncall_to_chat(bot, target_chat_id, schedule_name, shift)
                        logger.info("Sent oncall info to chat %s for schedule %s", target_chat_id, schedule_id)
                except Exception:
                    logger.exception("Failed to send oncall info to chat %s", target_chat_id)
            else:
                logger.warning("No target chat found for team_id %s", team_id)

        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={
                "status": "ok",
                "schedule_id": schedule_id,
                "schedule_name": schedule_name,
                "team_id": team_id,
                "shift": shift,
                "shifts": shifts,
                "sent_to_chat": bool(sent_flag)
            }
        )
    except Exception:
        logger.exception("Error in get_current_oncall_http")
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content={"status": "error", "detail": "Internal server error"}
        )


@app.get("/api/oncall/shifts")
async def get_oncall_shifts_http(
    schedule_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    send_to_chat: bool = False
) -> JSONResponse:
    """
    GET /api/oncall/shifts?schedule_id=SBRN8FTNETDZD&start_date=2025-11-11&end_date=2025-11-14
    
    Получить список смен за период.
    
    Args:
        schedule_id: ID расписания
        start_date: Начало периода (YYYY-MM-DD)
        end_date: Конец периода (YYYY-MM-DD)
        send_to_chat: Отправить результат в чат?
        
    Returns:
        JSON со списком смен
    """
    try:
        if not schedule_id:
            return JSONResponse(
                status_code=HTTPStatus.BAD_REQUEST,
                content={"status": "error", "detail": "schedule_id is required"}
            )
        
            logger.info(
                "get_oncall_shifts_http called with schedule_id=%s, start_date=%s, end_date=%s",
                schedule_id, start_date, end_date
            )
        
            # Получаем информацию о расписании
        schedule_info = await fetch_schedule_info(schedule_id)
        schedule_name = schedule_info.get("name", "Unknown")
        team_id = schedule_info.get("team_id")
        
        # Получаем смены
        shifts_data = await fetch_current_oncall(schedule_id, start_date, end_date)
        
        # Нормализуем ответ
        shifts = []
        if isinstance(shifts_data, dict):
            if "results" in shifts_data:
                shifts = shifts_data["results"]
            elif "shifts" in shifts_data:
                shifts = shifts_data.get("shifts", [])
        elif isinstance(shifts_data, list):
            shifts = shifts_data
        
        # Отправляем в чат если нужно
        if send_to_chat and shifts:
            event_data = {"team_id": team_id} if team_id else {}
            target_chat_id = chat_router.get_chat_id(event_data)
            
            if target_chat_id:
                text = format_oncall_day_summary(shifts)
                await send_message_to_chat(bot, target_chat_id, text)
                logger.info("Sent shifts list to chat %s for schedule %s", target_chat_id, schedule_id)
        
        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={
                "status": "ok",
                "schedule_id": schedule_id,
                "schedule_name": schedule_name,
                "team_id": team_id,
                "shifts_count": len(shifts),
                "shifts": shifts[:10],  # Максимум 10 смен в ответе
                "sent_to_chat": send_to_chat and bool(target_chat_id) if send_to_chat else False
            }
        )
    except Exception:
        logger.exception("Error in get_oncall_shifts_http")
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content={"status": "error", "detail": "Internal server error"}
        )