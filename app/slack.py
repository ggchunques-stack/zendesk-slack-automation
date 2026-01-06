import logging
from typing import Any, Dict, List

import httpx

from app.settings import get_settings

logger = logging.getLogger(__name__)


async def send_slack_alert(text: str, channel: str | None = None) -> None:
    settings = get_settings()
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.warning("Missing SLACK_WEBHOOK_URL; skipping notification")
        return

    payload: Dict[str, Any] = {"text": text}
    if channel:
        payload["channel"] = channel

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.exception("Failed to send Slack alert: %s", exc)


async def send_decision_alert(decision_dict: Dict[str, Any], payload: Dict[str, Any]) -> None:
    settings = get_settings()
    ticket_id = payload.get("ticket_id")
    ticket_id_text = str(ticket_id) if ticket_id is not None else "unknown"
    route_to = decision_dict.get("route_to") or "unknown"
    severity = decision_dict.get("severity") or "unknown"
    group_id = decision_dict.get("group_id")
    assignee_id = decision_dict.get("assignee_id")
    slack_channel = decision_dict.get("slack_channel")
    reason = decision_dict.get("reason") or "n/a"
    tags: List[str] = decision_dict.get("tags") or []

    ticket_url = None
    if settings.ZENDESK_SUBDOMAIN and ticket_id is not None:
        ticket_url = (
            f"https://{settings.ZENDESK_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket_id}"
        )

    assignment_bits = []
    if group_id is not None:
        assignment_bits.append(f"group_id: {group_id}")
    if assignee_id is not None:
        assignment_bits.append(f"assignee_id: {assignee_id}")
    assignment_text = ", ".join(assignment_bits) if assignment_bits else "unassigned"

    header = {"type": "header", "text": {"type": "plain_text", "text": "Zendesk Automation Alert"}}
    section_fields = [
        {"type": "mrkdwn", "text": f"*Ticket:*\n{ticket_id_text}"},
        {"type": "mrkdwn", "text": f"*Route:*\n{route_to}"},
        {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
        {"type": "mrkdwn", "text": f"*Assignment:*\n{assignment_text}"},
    ]
    if ticket_url:
        section_fields.append({"type": "mrkdwn", "text": f"*Link:*\n{ticket_url}"})

    section = {"type": "section", "fields": section_fields}
    context_items = [
        {"type": "mrkdwn", "text": f"*Reason:* {reason}"},
        {"type": "mrkdwn", "text": f"*Tags:* {', '.join(tags) if tags else 'n/a'}"},
    ]
    context = {"type": "context", "elements": context_items}

    blocks = [header, section, context]
    text = f"Zendesk alert: Ticket {ticket_id_text} routed to {route_to} ({severity})"
    payload_json: Dict[str, Any] = {"text": text, "blocks": blocks}
    if slack_channel:
        payload_json["channel"] = slack_channel

    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.warning("Missing SLACK_WEBHOOK_URL; skipping notification")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload_json)
            response.raise_for_status()
    except Exception as exc:
        logger.exception("Failed to send Slack decision alert: %s", exc)


async def ping_slack(text: str, channel: str | None = None) -> Dict[str, Any]:
    settings = get_settings()
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        return {"ok": False, "error": "Missing SLACK_WEBHOOK_URL"}

    payload: Dict[str, Any] = {"text": text}
    if channel:
        payload["channel"] = channel

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code >= 400:
                return {"ok": False, "status": response.status_code, "error": response.text}
            return {"ok": True, "status": response.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
