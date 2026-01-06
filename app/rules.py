from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# --------- Modelo de decisão (o "plano" do que fazer) ---------

@dataclass
class Decision:
    route_to: str                 # ex: "finance", "support", "stream_ops"
    severity: str                 # ex: "low", "normal", "high", "critical"
    tags: List[str]               # tags sugeridas
    notify: bool                  # se deve notificar Slack
    reason: str                   # explicação humana da decisão (ótimo pra logs)
    summary: str                  # resumo curto (ótimo pro Slack)


# --------- Helpers ---------

def _norm_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()

def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --------- Regras principais ---------

# Mapeia "type" => equipe/rota
TYPE_TO_ROUTE = {
    "billing": "finance",
    "refund": "finance",
    "payment": "finance",

    "technical": "support",
    "tech": "support",
    "bug": "support",

    "stream": "stream_ops",
    "stream_quality": "stream_ops",
    "event_day": "stream_ops",

    "account": "account_mgmt",
    "subscription": "account_mgmt",
}

# Normaliza prioridade => severidade
PRIORITY_TO_SEVERITY = {
    "low": "low",
    "normal": "normal",
    "medium": "normal",
    "high": "high",
    "urgent": "critical",
    "critical": "critical",
    "p1": "critical",
    "p2": "high",
    "p3": "normal",
    "p4": "low",
}

def evaluate(payload: Dict[str, Any]) -> Decision:
    """
    Recebe payload do webhook e retorna uma Decision com o que fazer.
    Esperado (mínimo):
      - ticket_id
      - type (categoria)
      - priority
    Mas funciona com payload incompleto (cai em defaults).
    """
    ticket_id = _safe_int(payload.get("ticket_id"))
    ticket_type = _norm_str(payload.get("type")) or "unknown"
    priority = _norm_str(payload.get("priority")) or "normal"

    # 1) Base routing por type
    route_to = TYPE_TO_ROUTE.get(ticket_type, "support")

    # 2) Severidade por prioridade
    severity = PRIORITY_TO_SEVERITY.get(priority, "normal")

    # 3) Tags sugeridas (padrão)
    tags: List[str] = []
    tags.append(f"type:{ticket_type}")
    tags.append(f"priority:{priority}")
    tags.append(f"route:{route_to}")
    tags.append(f"severity:{severity}")

    # 4) Ajustes por combinações (onde mora a magia)
    reason_parts: List[str] = []

    if ticket_type in ("billing", "refund", "payment"):
        reason_parts.append("Billing-related issue → Finance")
        tags.append("needs_finance")

    if ticket_type in ("stream", "stream_quality", "event_day"):
        reason_parts.append("Live/event issue → Stream Ops")
        tags.append("event_day_risk")

    # Se for high/critical, sempre notifica
    notify = severity in ("high", "critical")
    if notify:
        reason_parts.append("High severity → Slack notify")
        tags.append("slack_notify")

    # Se não tiver ticket_id, marca pra triagem (bom pra robustez)
    if ticket_id is None:
        reason_parts.append("Missing ticket_id → needs_triage")
        tags.append("needs_triage")

    # Mensagens curtas e úteis
    summary_ticket = f"Ticket #{ticket_id}" if ticket_id is not None else "Ticket (no id)"
    summary = f"{summary_ticket} → {route_to} | {ticket_type} | {priority} ({severity})"

    reason = " | ".join(reason_parts) if reason_parts else "Default routing rules applied"

    return Decision(
        route_to=route_to,
        severity=severity,
        tags=tags,
        notify=notify,
        reason=reason,
        summary=summary,
    )