# ...existing code...
from typing import Dict, Any, List, Optional

def format_alerts_list(api_response: Dict[str, Any], max_items: int = 5) -> str:
    """
    Форматирует ответ от Grafana OnCall для вывода в чат.
    Поддерживает ответы с полем 'results' или 'alerts' и т.д.
    """
    alerts: List[Dict[str, Any]] = []
    if isinstance(api_response, dict):
        if "alerts" in api_response and isinstance(api_response["alerts"], list):
            alerts = api_response["alerts"]
        elif "results" in api_response and isinstance(api_response["results"], list):
            alerts = api_response["results"]
        elif "data" in api_response and isinstance(api_response["data"], list):
            alerts = api_response["data"]
        else:
            for v in api_response.values():
                if isinstance(v, list):
                    alerts = v
                    break
    elif isinstance(api_response, list):
        alerts = api_response

    if not alerts:
        return "✅ Нет активных алертов."

    total = len(alerts)
    shown = min(total, max_items)
    lines = [f"📋 Найдено алертов: {total} (показано {shown}):\n"]

    for a in alerts[:max_items]:
        aid = a.get("id", "N/A")
        title = (a.get("title") or "").strip() or "No title"
        state = a.get("state") or a.get("status") or "unknown"
        alerts_count = a.get("alerts_count") or a.get("numFiring") or ""
        created = a.get("created_at") or a.get("last_alert", {}).get("created_at") or ""
        permalinks = a.get("permalinks") or {}
        web_link = permalinks.get("web") or a.get("last_alert", {}).get("payload", {}).get("groupKey", "") or ""

        # Попытка достать summary/annotation из last_alert.payload.alerts[0].annotations.title
        last_alert = a.get("last_alert") or {}
        payload = last_alert.get("payload") or {}
        common_labels = payload.get("commonLabels") or {}
        num_firing = payload.get("numFiring") or payload.get("num_firing") or ""

        summary = ""
        if payload.get("alerts") and isinstance(payload["alerts"], list) and payload["alerts"]:
            ann = payload["alerts"][0].get("annotations", {}) or {}
            summary = ann.get("title") or ann.get("description") or ""

        # Формируем строку
        line = f"• [{aid}] {title} — {state}"
        if alerts_count:
            line += f" | alerts: {alerts_count}"
        if num_firing:
            line += f" | firing: {num_firing}"
        if created:
            line += f"\n  ⏱ {created}"
        if web_link:
            line += f"\n  🔗 {web_link}"
        if summary:
            line += f"\n  📝 {summary}"
        if common_labels:
            # Ограничим вывод меток
            lbls = ", ".join(f"{k}={v}" for k, v in list(common_labels.items())[:5])
            line += f"\n  🏷 {lbls}"
        lines.append(line)

    return "\n\n".join(lines)
# ...existing code...

def _format_labels_section(title: str, labels: Dict[str, Any]) -> str:
    if not labels:
        return ""
    lines = [f"{title}:"]
    for k, v in labels.items():
        lines.append(f"  • {k}: {v}")
    return "\n".join(lines) + "\n\n"

def format_escalation_message(
    short_id: str,
    title: str,
    username: str,
    alerts_count: int,
    state: str,
    num_firing: int,
    num_resolved: int,
    integration_name: str,
    permalink: str,
    group_labels: Dict,
    common_labels: Dict,
    annotations: Dict = None,
    severity: str = None
) -> str:
    """Форматирует сообщение для события escalation (новый алерт)"""
    state_emoji = "🚨" if state == "firing" else "⚠️"
    severity_emoji = {
        "critical": "🔴",
        "warning": "🟡",
        "info": "🔵",
        "unknown": "⚪"
    }.get((severity or "").lower(), "⚪")
    
    lines = [
        f"{state_emoji} ESCALATION: {title}",
        ""
    ]
    
    # Severity и основная информация
    if severity:
        lines.append(f"{severity_emoji} Severity: {severity.upper()}")
    lines.append(f"📊 State: {state.upper()} | Alerts: {alerts_count}")
    
    if num_firing or num_resolved:
        lines.append(f"🔥 Firing: {num_firing} | ✅ Resolved: {num_resolved}")
    
    # Аннотации (message/summary)
    if annotations:
        message = annotations.get("message") or annotations.get("summary") or ""
        if message:
            lines.append(f"💬 {message}")
    
    # Детали
    lines.extend([
        "",
        f"📍 Integration: {integration_name}",
        f"🔗 {permalink}"
    ])
    
    # Labels в компактном виде
    if group_labels:
        labels_str = ", ".join(f"{k}={v}" for k, v in list(group_labels.items())[:6])
        lines.append(f"🏷 {labels_str}")
    
    return "\n".join(lines)

def format_acknowledge_message(
    short_id: str, title: str, username: str, alerts_count: int, state: str, 
    num_firing: int, num_resolved: int, integration_name: str, permalink: str,
    group_labels: Dict, common_labels: Dict, annotations: Dict = None
) -> str:
    """Форматирует сообщение для события acknowledge"""
    lines = [
        f"✅ ACKNOWLEDGED: {title}",
        ""
    ]
    
    if username:
        lines.append(f"👤 By: {username}")
    
    lines.extend([
        f"📊 State: {state.upper()}",
        f"🔗 {permalink}"
    ])
    
    return "\n".join(lines)

def format_resolve_message(
    short_id: str, title: str, username: str, alerts_count: int, state: str,
    num_firing: int, num_resolved: int, integration_name: str, permalink: str,
    group_labels: Dict, common_labels: Dict, annotations: Dict = None
) -> str:
    """Форматирует сообщение для события resolve"""
    lines = [
        f"🟢 RESOLVED: {title}",
        ""
    ]
    
    if username:
        lines.append(f"👤 Resolved by: {username}")
    
    lines.extend([
        f"📊 State: {state.upper()}",
        f"🔗 {permalink}"
    ])
    
    return "\n".join(lines)

def format_unacknowledge_message(
    short_id: str, title: str, username: str, alerts_count: int, state: str,
    num_firing: int, num_resolved: int, integration_name: str, permalink: str,
    group_labels: Dict, common_labels: Dict, annotations: Dict = None
) -> str:
    """Форматирует сообщение для события unacknowledge"""
    lines = [
        f"ℹ️ UNACKNOWLEDGED: {title}",
        f"👤 By: {username or 'unknown'}",
        f"🔗 {permalink}"
    ]
    return "\n".join(lines)

def format_unresolve_message(
    short_id: str, title: str, username: str, alerts_count: int, state: str,
    num_firing: int, num_resolved: int, integration_name: str, permalink: str,
    group_labels: Dict, common_labels: Dict, annotations: Dict = None
) -> str:
    """Форматирует сообщение для события unresolve"""
    lines = [
        f"🔴 REOPENED: {title}",
        f"👤 By: {username or 'unknown'}",
        f"🔗 {permalink}"
    ]
    return "\n".join(lines)

def format_silence_message(
    short_id: str, title: str, username: str, alerts_count: int, state: str,
    num_firing: int, num_resolved: int, integration_name: str, permalink: str,
    group_labels: Dict, common_labels: Dict, until: str = None, annotations: Dict = None
) -> str:
    """Форматирует сообщение для события silence"""
    until_text = f" until {until}" if until else ""
    lines = [
        f"🔕 SILENCED{until_text.upper() if until_text else ''}: {title}",
        f"👤 By: {username or 'unknown'}",
        f"🔗 {permalink}"
    ]
    return "\n".join(lines)

def format_unsilence_message(
    short_id: str, title: str, username: str, alerts_count: int, state: str,
    num_firing: int, num_resolved: int, integration_name: str, permalink: str,
    group_labels: Dict, common_labels: Dict, annotations: Dict = None
) -> str:
    """Форматирует сообщение для события unsilence"""
    lines = [
        f"🔔 UNSILENCED: {title}",
        f"👤 By: {username or 'unknown'}",
        f"🔗 {permalink}"
    ]
    return "\n".join(lines)

def format_unknown_event_message(event_type: str, title: str, short_id: str) -> str:
    return f"❓ [{short_id}] Unknown event '{event_type}' for alert '{title}'"