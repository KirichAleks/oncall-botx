import logging
import json
from typing import Optional, Dict, Any
from pydantic import BaseSettings, Field, validator

# ...existing code...
class Settings(BaseSettings):
    """Настройки приложения (берутся из окружения или .env)"""
    botx_bot_id: str = Field(..., env="BOTX_BOT_ID")
    botx_host: str = Field("http://localhost:8080", env="BOTX_HOST")
    botx_secret_key: str = Field(..., env="BOTX_SECRET_KEY")
    
    # Для обратной совместимости - если указан, используется как fallback
    target_chat_id: Optional[str] = Field(None, env="TARGET_CHAT_ID")
    
    # Новая система маршрутизации: JSON строка с маппингом integration_name -> chat_id
    # Пример: {"backend-team": "uuid-1", "frontend-team": "uuid-2"}
    chat_routing_config: Optional[str] = Field(None, env="CHAT_ROUTING_CONFIG")
    
    # Отдельные переменные для каждой команды (альтернатива JSON)
    # Пример: CHAT_ROUTING_BACKEND_TEAM=uuid-1, CHAT_ROUTING_FRONTEND_TEAM=uuid-2
    # Собираются автоматически
    
    webhook_secret: Optional[str] = Field(None, env="WEBHOOK_SECRET")
    # Новые настройки для Grafana OnCall
    grafana_oncall_url: Optional[str] = Field(None, env="GRAFANA_ONCALL_URL")
    grafana_oncall_token: Optional[str] = Field(None, env="GRAFANA_ONCALL_TOKEN")
    grafana_oncall_timeout: int = Field(10, env="GRAFANA_ONCALL_TIMEOUT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
# ...existing code...

    @validator("log_level", pre=True, always=True)
    def validate_log_level(cls, v):
        level = str(v).upper()
        if level not in logging._nameToLevel:
            raise ValueError(f"invalid log level: {v}")
        return level
    
    def get_chat_routing(self) -> Dict[str, str]:
        """
        Получить словарь маршрутизации: integration_name -> chat_id
        
        Приоритет:
        1. CHAT_ROUTING_CONFIG (JSON строка)
        2. Отдельные переменные CHAT_ROUTING_*
        3. Fallback на TARGET_CHAT_ID (для совместимости)
        """
        routing = {}
        
        # Проверяем JSON config
        if self.chat_routing_config:
            try:
                routing = json.loads(self.chat_routing_config)
                if not isinstance(routing, dict):
                    logging.getLogger(__name__).warning(
                        "CHAT_ROUTING_CONFIG is not a valid JSON object, ignoring"
                    )
                    routing = {}
            except json.JSONDecodeError as e:
                logging.getLogger(__name__).warning(
                    f"Failed to parse CHAT_ROUTING_CONFIG as JSON: {e}"
                )
        
        return routing

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()