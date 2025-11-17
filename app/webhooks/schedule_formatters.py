import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


def format_oncall_person(person: Dict[str, Any]) -> str:
    """
    Форматировать информацию о дежурном.
    
    Args:
        person: Словарь с информацией о пользователе
        
    Returns:
        Отформатированная строка
    """
    # Support different schemas: nested `user` or flat fields like `user_username`/`user_email`.
    if not person:
        # attempt to handle flat-shift entries where user fields are on parent dict
        name = "Unknown"
        username = ""
    else:
        name = person.get("name") or person.get("user_email") or person.get("user_username") or "Unknown"
        username = person.get("username") or person.get("user_username") or ""
    
    if username:
        return f"👤 {name} (@{username})"
    return f"👤 {name}"


def format_shift(shift: Dict[str, Any]) -> str:
    """
    Форматировать информацию о смене.
    
    Args:
        shift: Словарь с информацией о смене
        
    Returns:
        Отформатированная строка
    """
    # Support multiple possible field names returned by different scheduler APIs
    start_time = (
        shift.get("start")
        or shift.get("start_time")
        or shift.get("shift_start")
        or shift.get("shift_start_time")
        or ""
    )
    end_time = (
        shift.get("end")
        or shift.get("end_time")
        or shift.get("shift_end")
        or shift.get("shift_end_time")
        or ""
    )
    
    lines = []
    if start_time:
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            lines.append(f"⏰ Начало: {dt.strftime('%d.%m.%Y %H:%M')}")
        except Exception:
            lines.append(f"⏰ Начало: {start_time}")
    
    if end_time:
        try:
            dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            lines.append(f"⏳ Конец: {dt.strftime('%d.%m.%Y %H:%M')}")
        except Exception:
            lines.append(f"⏳ Конец: {end_time}")
    
    return "\n".join(lines)


def format_current_oncall(shift_data: Dict[str, Any], schedule_name: str = "") -> str:
    """
    Форматировать информацию о текущем дежурном.
    
    Args:
        shift_data: Данные о смене от API
        schedule_name: Имя расписания (опционально)
        
    Returns:
        Отформатированная строка для отправки в чат
    """
    lines = []
    
    # Заголовок
    if schedule_name:
        lines.append(f"📅 Расписание: {schedule_name}")
    lines.append("👀 Текущий дежурный:")
    lines.append("")
    
    # Извлекаем информацию о пользователе.
    # Some scheduler responses have user info under `user`, others provide flat fields.
    user = shift_data.get("user") or {
        "user_username": shift_data.get("user_username"),
        "user_email": shift_data.get("user_email"),
        "name": shift_data.get("user_email") or shift_data.get("user_username"),
    }
    person_info = format_oncall_person(user)
    if person_info:
        lines.append(person_info)
    
    # Информация о смене
    shift_info = format_shift(shift_data)
    if shift_info:
        lines.append("")
        lines.append(shift_info)
    
    return "\n".join(lines)


def format_oncall_list(shifts_data: List[Dict[str, Any]], schedule_name: str = "", max_items: int = 5) -> str:
    """
    Форматировать список дежурных.
    
    Args:
        shifts_data: Список смен от API
        schedule_name: Имя расписания
        max_items: Максимум элементов для отображения
        
    Returns:
        Отформатированная строка
    """
    if not shifts_data:
        return "❌ Нет информации о дежурных"
    
    lines = []
    
    # Заголовок
    if schedule_name:
        lines.append(f"📅 Расписание: {schedule_name}")
    lines.append("👀 Дежурные по очереди:")
    lines.append("")
    
    # Выводим первых max_items
    for i, shift in enumerate(shifts_data[:max_items], 1):
        # Build a user dict that works with format_oncall_person
        user = shift.get("user") or {
            "user_username": shift.get("user_username"),
            "user_email": shift.get("user_email"),
            "name": shift.get("user_email") or shift.get("user_username"),
        }
        lines.append(f"{i}. {format_oncall_person(user)}")

        # Время смены (support different field names)
        start_time = (
            shift.get("start")
            or shift.get("start_time")
            or shift.get("shift_start")
            or ""
        )
        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                lines.append(f"   ⏰ {dt.strftime('%d.%m.%Y %H:%M')}")
            except Exception:
                # Fallback: just append the raw value
                lines.append(f"   ⏰ {start_time}")
    
    if len(shifts_data) > max_items:
        lines.append(f"\n... и еще {len(shifts_data) - max_items} смен")
    
    return "\n".join(lines)
