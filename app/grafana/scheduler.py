import logging
from typing import Optional, Dict, Any, List
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def fetch_current_oncall(
    schedule_id: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получить информацию о дежурных из Grafana OnCall Scheduler.
    
    Args:
        schedule_id: ID расписания в Grafana OnCall
        start_date: Начальная дата в формате YYYY-MM-DD (опционально)
        end_date: Конечная дата в формате YYYY-MM-DD (опционально)
        
    Returns:
        Словарь с информацией о дежурных
    """
    if not settings.grafana_oncall_url:
        raise RuntimeError("GRAFANA_ONCALL_URL not configured")
    
    if not settings.grafana_oncall_token:
        raise RuntimeError("GRAFANA_ONCALL_TOKEN not configured")

    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = settings.grafana_oncall_token

    timeout = httpx.Timeout(settings.grafana_oncall_timeout, connect=settings.grafana_oncall_timeout)
    
    # Получаем дежурных из final_shifts
    url = settings.grafana_oncall_url.rstrip("/") + f"/api/v1/schedules/{schedule_id}/final_shifts/"
    
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    
        logger.info(
            "fetch_current_oncall: schedule_id=%s, params=%s, url=%s",
            schedule_id, params, url
        )

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} when fetching oncall: {e.response.text}")
            raise
        except Exception:
            logger.exception("Error calling Grafana OnCall Scheduler API")
            raise


async def fetch_schedule_info(schedule_id: str) -> Dict[str, Any]:
    """
    Получить информацию о расписании.
    
    Args:
        schedule_id: ID расписания в Grafana OnCall
        
    Returns:
        Словарь с информацией о расписании
    """
    if not settings.grafana_oncall_url:
        raise RuntimeError("GRAFANA_ONCALL_URL not configured")
    
    if not settings.grafana_oncall_token:
        raise RuntimeError("GRAFANA_ONCALL_TOKEN not configured")

    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = settings.grafana_oncall_token

    timeout = httpx.Timeout(settings.grafana_oncall_timeout, connect=settings.grafana_oncall_timeout)
    
    url = settings.grafana_oncall_url.rstrip("/") + f"/api/v1/schedules/{schedule_id}/"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data
        except Exception:
            logger.exception("Error calling Grafana OnCall Scheduler API")
            raise


async def fetch_all_schedules() -> List[Dict[str, Any]]:
    """
    Получить список всех расписаний.
    
    Returns:
        Список расписаний
    """
    if not settings.grafana_oncall_url:
        raise RuntimeError("GRAFANA_ONCALL_URL not configured")
    
    if not settings.grafana_oncall_token:
        raise RuntimeError("GRAFANA_ONCALL_TOKEN not configured")

    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = settings.grafana_oncall_token

    timeout = httpx.Timeout(settings.grafana_oncall_timeout, connect=settings.grafana_oncall_timeout)
    
    url = settings.grafana_oncall_url.rstrip("/") + "/api/v1/schedules/"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            # Нормализуем ответ
            if isinstance(data, dict):
                if "results" in data:
                    return data["results"]
                elif "schedules" in data:
                    return data["schedules"]
                elif "data" in data and isinstance(data["data"], list):
                    return data["data"]
            if isinstance(data, list):
                return data
            
            return []
        except Exception:
            logger.exception("Error fetching schedules from Grafana OnCall API")
            raise
