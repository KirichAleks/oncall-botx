from typing import Dict, Any, List, Optional
from app.config import settings

def format_oncall_webhook_message(event_data: Dict[str, Any]) -> str:
    """Форматирует сообщение для чата по шаблону пользователя.

    Правила (по требованию пользователя):
    - Start / Group Labels / Common Labels показываются только для escalation.
    - Для resolve показываем Start и Resolved (но без Labels).
    - Для остальных типов этих блоков нет.
    - Внешний base URL берём из settings (EXT_GRAFANA_URL приоритетно, затем GRAFANA_ONCALL_URL).
    """
    alert_group = event_data.get("alert_group", {})
    alert_payload = event_data.get("alert_payload", {})
    event = event_data.get("event", {})
    raw_user = event_data.get("user")
    user = raw_user if isinstance(raw_user, dict) and raw_user else {}
    team_id = alert_group.get("team_id") or event_data.get("team_id")
    group_id = alert_group.get("id", "N/A")
    # Используем alertname вместо длинного title
    alertname = None
    if alert_payload.get("alerts") and isinstance(alert_payload["alerts"], list) and alert_payload["alerts"]:
        alertname = alert_payload["alerts"][0].get("labels", {}).get("alertname")
    if not alertname:
        alertname = (alert_payload.get("groupLabels") or {}).get("alertname")
    if not alertname:
        alertname = (alert_payload.get("commonLabels") or {}).get("alertname")
    if not alertname:
        alertname = alert_group.get("title") or alert_group.get("name") or ""
    title = alertname
    state = (alert_group.get("state") or event.get("type") or "").lower()
    event_type = (event.get("type") or state or "").lower()
    # Отображение статуса ориентируем на event_type, чтобы unsilence/unack/unresolve не выглядели как firing
    status_map = {
        "escalation": ("🚨", "Escalation"),
        "acknowledge": ("🟡", "Acknowledged"),
        "acknowledged": ("🟡", "Acknowledged"),
        "unacknowledge": ("⚪️", "Unacknowledged"),
        "unresolve": ("🔴", "Reopened"),
        "resolve": ("🟢", "Resolved"),
        "resolved": ("🟢", "Resolved"),
        "silence": ("🔕", "Silenced"),
        "unsilence": ("🔔", "Unsilenced"),
        # fallback на состояния группы, если тип события неизвестен
        "firing": ("🚨", "Firing"),
    }
    if event_type in status_map:
        emoji, status_text = status_map[event_type]
    else:
        emoji, status_text = status_map.get(state, ("❓", (event_type or state or "Event").capitalize()))
    # summary (annotation.summary)
    summary = ""
    # Ищем summary в alert_payload или alerts[0].annotations.summary
    if alert_payload.get("alerts") and isinstance(alert_payload["alerts"], list) and alert_payload["alerts"]:
        ann = alert_payload["alerts"][0].get("annotations", {}) or {}
        summary = ann.get("summary") or ""
    if not summary:
        summary = (alert_payload.get("commonAnnotations") or {}).get("summary") or ""
    # Если нет summary — оставить пустым
    # Количество алертов
    alerts_count = alert_group.get("alerts_count") or alert_payload.get("numFiring") or len(alert_payload.get("alerts", []))
    num_firing = alert_payload.get("numFiring") or 0
    num_resolved = alert_payload.get("numResolved") or 0
    # Labels
    group_labels_raw = alert_payload.get("groupLabels") or alert_group.get("labels") or {}
    group_labels = group_labels_raw if isinstance(group_labels_raw, dict) else {}
    common_labels_raw = alert_payload.get("commonLabels") or {}
    common_labels = common_labels_raw if isinstance(common_labels_raw, dict) else {}
    annotations_raw = alert_payload.get("commonAnnotations") or {}
    annotations = annotations_raw if isinstance(annotations_raw, dict) else {}
    # User
    username = user.get("username") or user.get("email") or ""
    # Ссылки
    base_url = (getattr(settings, "ext_grafana_url", None) or getattr(settings, "grafana_oncall_url", None) or "")
    current_url = f"{base_url}a/grafana-oncall-app/alert-groups/{group_id}" if base_url else ""
    all_url = f"{base_url}a/grafana-oncall-app/alert-groups?status=0&status=1&started_at=now-30d_now&team={team_id}" if base_url else ""
    # Время начала и резолва (если есть)
    # Для escalation: время начала (created_at или alerts[0]["startsAt"])
    # Для resolve: время начала и resolved_at
    start_time = None
    resolved_time = None
    if alert_group.get("created_at"):
        start_time = alert_group["created_at"]
    elif alert_payload.get("alerts") and isinstance(alert_payload["alerts"], list) and alert_payload["alerts"]:
        start_time = alert_payload["alerts"][0].get("startsAt")
    if alert_group.get("resolved_at"):
        resolved_time = alert_group["resolved_at"]

    # Хелпер для форматирования времени: HH:MM:SS DD.MM.YY
    from datetime import datetime as _dt
    def _fmt_ts(ts: Optional[str]) -> Optional[str]:
        if not ts:
            return None
        try:
            iso = ts.replace("Z", "+00:00")
            dt = _dt.fromisoformat(iso)
            return dt.strftime("%H:%M:%S %d.%m.%y")
        except Exception:
            # если не ISO, вернуть как есть
            return ts

    # Формируем сообщение
    lines = [
        f"{emoji} #{group_id} - {title}{f' ({summary})' if summary else ''}",
        f"Status: {status_text}",
    ]
    # Время для escalation
    # Start/Resolved/Counts/Labels по правилам
    if event_type == "escalation" and start_time:
        ft = _fmt_ts(start_time)
        lines.append(f"Start: {ft}")
    elif event_type in ("resolve", "resolved"):
        if start_time:
            lines.append(f"Start: {_fmt_ts(start_time)}")
        if resolved_time:
            lines.append(f"Resolve: {_fmt_ts(resolved_time)}")
    elif event_type == "silence":
        # Для silence показать диапазон: от времени события/"silenced_at" до event.until
        st = event.get("time") or alert_group.get("silenced_at") or start_time
        until = event.get("until")
        if st:
            lines.append(f"Start: {_fmt_ts(st)}")
        if until:
            lines.append(f"Resolve: {_fmt_ts(until)}")
    if event_type == "escalation":
        lines.append(f"Alerts in group: {alerts_count} | Firing: {num_firing} | Resolved: {num_resolved}")
        if group_labels:
            lines.append("")
            lines.append("Group Labels:")
            for k, v in group_labels.items():
                lines.append(f"  - {k}: {v}")
        if common_labels:
            lines.append("")
            lines.append("Common Labels:")
            for k, v in common_labels.items():
                lines.append(f"  - {k}: {v}")
    if annotations:
        lines.append("Annotations:")
        for k, v in annotations.items():
            lines.append(f" - {k}: \"{v}\"")
    if event_type in ("acknowledge", "acknowledged", "resolve", "resolved", "unacknowledge", "unresolve", "silence", "unsilence"):
        lines.append("")
        lines.append(f"By: {username}")
    lines.append("")
    if current_url:
        lines.append(f"[View current alert group]({current_url})")
    if all_url:
        lines.append(f"[View all alert group]({all_url})")
    return "\n".join(lines)
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
        "error": "🔴",
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