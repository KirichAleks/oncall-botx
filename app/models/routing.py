"""
Модуль для управления маршрутизацией сообщений Grafana OnCall в разные чаты.

Позволяет направлять сообщения от разных интеграций в разные чаты на основе:
- Имени интеграции (integration_name)
- ID интеграции (integration_id)
- Других полей события
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ChatRouter:
    """
    Маршрутизатор для определения целевого чата на основе события Grafana OnCall.
    
    Использует конфигурацию маршрутизации для направления сообщений в разные чаты
    в зависимости от интеграции.
    """

    def __init__(self, routing_config: Dict[str, str], fallback_chat_id: Optional[str] = None):
        """
        Инициализация маршрутизатора.
        
        Args:
            routing_config: Словарь {integration_name -> chat_id} или {integration_id -> chat_id}
            fallback_chat_id: Fallback chat_id если маршрут не найден
        """
        self.routing_config = routing_config or {}
        self.fallback_chat_id = fallback_chat_id
        
        logger.info(
            "ChatRouter initialized with %d routes. Fallback: %s",
            len(self.routing_config),
            self.fallback_chat_id or "none"
        )

    def get_chat_id(self, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Определить целевой chat_id для события OnCall по team_id.
        
        Порядок поиска team_id:
        1. event_data["alert_group"]["team_id"] — для webhook событий
        2. event_data["team_id"] — для прямых вызовов
        3. event_data["schedule"]["team_id"] — для scheduler операций
        
        Args:
            event_data: Полное событие от Grafana OnCall или данные о расписании
            
        Returns:
            UUID чата в виде строки или None если не найден подходящий маршрут
        """
        # Извлекаем team_id из разных возможных мест
        team_id = None
        
        # Первый приоритет: alert_group.team_id (webhook события)
        alert_group = event_data.get("alert_group") or {}
        if isinstance(alert_group, dict):
            team_id = alert_group.get("team_id")
        
        # Второй приоритет: top-level team_id
        if not team_id:
            team_id = event_data.get("team_id")
        
        # Третий приоритет: schedule.team_id (scheduler операции)
        if not team_id:
            schedule = event_data.get("schedule") or {}
            if isinstance(schedule, dict):
                team_id = schedule.get("team_id")
        
        # Если team_id найден, ищем его в конфигурации
        if team_id:
            if team_id in self.routing_config:
                chat_id = self.routing_config[team_id]
                logger.debug(
                    "Found chat_id by team_id=%s -> %s",
                    team_id, chat_id
                )
                return chat_id
            else:
                logger.warning(
                    "team_id=%s not found in routing_config. Using fallback.",
                    team_id
                )
        else:
            logger.warning(
                "No team_id found in event data. Using fallback."
            )
        
        # Возвращаем fallback если существует
        if self.fallback_chat_id:
            logger.debug("Using fallback chat_id: %s", self.fallback_chat_id)
            return self.fallback_chat_id
        
        return None

    def validate_chat_id(self, chat_id: str) -> bool:
        """
        Проверить, что chat_id это валидный UUID.
        
        Args:
            chat_id: Строка для проверки
            
        Returns:
            True если валидный UUID, False иначе
        """
        try:
            UUID(chat_id)
            return True
        except (ValueError, TypeError):
            logger.warning("Invalid chat_id format (not a UUID): %s", chat_id)
            return False

    def get_routing_summary(self) -> str:
        """
        Получить текстовый отчёт о текущей маршрутизации.
        Полезно для логирования и отладки.
        """
        lines = ["Chat Routing Configuration (team_id -> chat_id):"]
        
        if self.routing_config:
            for team_id, chat_id in sorted(self.routing_config.items()):
                lines.append(f"  {team_id} → {chat_id}")
        else:
            lines.append("  (no routes configured)")
        
        if self.fallback_chat_id:
            lines.append(f"\nFallback chat_id: {self.fallback_chat_id}")
        else:
            lines.append("\nFallback: (none)")
        
        return "\n".join(lines)
