from typing import Any, Dict, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from app import config, rules, slack, storage, zendesk
from app.settings import get_settings
from app.webhook import _compute_expected_signatures, _extract_signature, _signature_matches

def _require_debug() -> None:
    settings = get_settings()
    if not settings.DEBUG_WEBHOOK_SIGNATURE:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_debug)])

@router.get("/zendesk/me")
async def zendesk_me():
    result = await zendesk.get_me()
    status_code = 200 if result.get("ok") else result.get("status", 500)
    return JSONResponse(status_code=status_code, content=result)

@router.get("/zendesk/tickets/{ticket_id}")
async def zendesk_ticket(ticket_id: int):
    result = await zendesk.get_ticket(ticket_id)
    status_code = 200 if result.get("ok") else result.get("status", 500)
    return JSONResponse(status_code=status_code, content=result)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str_list(value: Any) -> list[str] | None:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [str(item).strip() for item in value if str(item).strip()]
    return None


@router.get("/decisions/recent")
async def decisions_recent(limit: int = Query(50, ge=1, le=500)):
    data = await run_in_threadpool(storage.fetch_recent_decisions, limit)
    return {"ok": True, "data": data}

@router.get("/events/recent")
async def events_recent(limit: int = Query(50, ge=1, le=500)):
    data = await run_in_threadpool(storage.fetch_recent_events, limit)
    return {"ok": True, "data": data}


@router.get("/decisions/replay")
async def decisions_replay(ticket_id: int = Query(..., ge=1)):
    payload = await run_in_threadpool(storage.fetch_latest_payload_for_ticket, ticket_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="No decision payload found for ticket_id")

    decision = rules.evaluate(payload)
    route_cfg = config.get_route_config(decision.route_to)
    group_id = _safe_int(route_cfg.get("group_id"))
    assignee_id = _safe_int(route_cfg.get("assignee_id"))
    slack_channel = route_cfg.get("slack_channel")
    notify_on = _safe_str_list(route_cfg.get("notify_on"))

    notify = decision.notify
    if notify_on is not None:
        notify = decision.severity in notify_on

    decision_dict: Dict[str, Any] = {
        "route_to": decision.route_to,
        "severity": decision.severity,
        "notify": notify,
        "summary": decision.summary,
        "reason": decision.reason,
        "tags": decision.tags,
        "group_id": group_id,
        "assignee_id": assignee_id,
        "slack_channel": slack_channel,
    }

    return {"ok": True, "ticket_id": ticket_id, "decision": decision_dict}


@router.get("/reports/metrics.csv")
async def reports_metrics_csv():
    csv_text = await run_in_threadpool(storage.generate_metrics_csv)
    return Response(content=csv_text, media_type="text/csv")


@router.post("/signature-check")
async def signature_check(request: Request):
    settings = get_settings()

    secret = settings.ZENDESK_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=400, detail="Missing ZENDESK_WEBHOOK_SECRET")

    body = await request.body()
    signature_entry = _extract_signature(request.headers, settings.SIGNATURE_HEADER_CANDIDATES)
    received_signature = signature_entry[1] if signature_entry else None
    timestamp = request.headers.get(settings.SIGNATURE_TIMESTAMP_HEADER)

    expected_hex, expected_b64 = _compute_expected_signatures(secret, timestamp or "", body)
    match = False
    if received_signature and timestamp:
        match = _signature_matches(received_signature, expected_hex, expected_b64)

    return {
        "received_signature": received_signature,
        "timestamp": timestamp,
        "computed_signature_hex": expected_hex,
        "computed_signature_b64": expected_b64,
        "match": match,
    }


@router.post("/ping-slack")
async def ping_slack(
    message: str | None = Query(None),
    channel: str | None = Query(None),
):
    settings = get_settings()
    text = message or "Zendesk automation debug ping"
    result = await slack.ping_slack(text, channel=channel)
    status_code = 200 if result.get("ok") else result.get("status", 500)
    return JSONResponse(status_code=status_code, content=result)
