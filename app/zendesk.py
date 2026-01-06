import asyncio
import json
import logging
import httpx
from typing import Any, Dict, List, Optional, Tuple

from app.settings import get_settings

logger = logging.getLogger(__name__)
def _base_url() -> str:
    settings = get_settings()
    if not settings.ZENDESK_SUBDOMAIN:
        return ""
    return f"https://{settings.ZENDESK_SUBDOMAIN}.zendesk.com/api/v2"

def _auth() -> Optional[Tuple[str, str]]:
    settings = get_settings()
    if not (settings.ZENDESK_EMAIL and settings.ZENDESK_API_TOKEN):
        return None
    return (f"{settings.ZENDESK_EMAIL}/token", settings.ZENDESK_API_TOKEN)

def build_ticket_update_payload(
    *,
    tags: Optional[List[str]] = None,
    comment: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[int] = None,
    group_id: Optional[int] = None,
    add_internal_comment: bool = True,
) -> Dict[str, Any]:
    ticket: Dict[str, Any] = {}
    if tags:
        ticket["tags"] = tags
    if comment and add_internal_comment:
        ticket["comment"] = {"body": comment, "public": False}
    if status:
        ticket["status"] = status
    if priority:
        ticket["priority"] = priority
    if group_id is not None:
        ticket["group_id"] = group_id
    if assignee_id is not None:
        ticket["assignee_id"] = assignee_id
    return {"ticket": ticket}

async def get_me() -> Dict[str, Any]:
    url = f"{_base_url()}/users/me.json"
    auth = _auth()
    if not auth or not url:
        return {"ok": False, "error": "Missing Zendesk credentials/subdomain"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, auth=auth)
            if r.status_code >= 400:
                return {"ok": False, "status": r.status_code, "error": r.text}
            return {"ok": True, "status": r.status_code, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def get_ticket(ticket_id: int) -> Dict[str, Any]:
    url = f"{_base_url()}/tickets/{ticket_id}.json"
    auth = _auth()
    if not auth or not url:
        return {"ok": False, "error": "Missing Zendesk credentials/subdomain"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, auth=auth)
            if r.status_code >= 400:
                return {"ok": False, "status": r.status_code, "error": r.text}
            return {"ok": True, "status": r.status_code, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def update_ticket(
    ticket_id: int, payload: Dict[str, Any], dry_run: bool | None = None
) -> Dict[str, Any]:
    settings = get_settings()
    if dry_run is None:
        dry_run = settings.ZENDESK_DRY_RUN

    if dry_run:
        logger.info("Zendesk dry run: would PATCH ticket %s", ticket_id)
        logger.debug("Zendesk dry run payload: %s", json.dumps(payload, ensure_ascii=False))
        return {"ok": True, "status": 200, "data": {"dry_run": True}}

    url = f"{_base_url()}/tickets/{ticket_id}.json"
    auth = _auth()
    if not auth or not url:
        return {"ok": False, "error": "Missing Zendesk credentials/subdomain"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            backoffs = [0.5, 1.0, 2.0]
            last_error: Dict[str, Any] | None = None
            for attempt in range(len(backoffs) + 1):
                r = await client.patch(url, auth=auth, json=payload)
                if r.status_code >= 500:
                    last_error = {"ok": False, "status": r.status_code, "error": r.text}
                    if attempt < len(backoffs):
                        await asyncio.sleep(backoffs[attempt])
                        continue
                    return last_error
                if r.status_code >= 400:
                    return {"ok": False, "status": r.status_code, "error": r.text}
                return {"ok": True, "status": r.status_code, "data": r.json()}
            return last_error or {"ok": False, "error": "Unknown Zendesk error"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
