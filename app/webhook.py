import base64
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app import router as event_router
from app.settings import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _extract_signature(headers: dict, candidates: list[str]) -> tuple[str, str] | None:
    for name in candidates:
        value = headers.get(name)
        if value:
            return name, value
    return None


def _strip_signature_prefix(signature: str) -> str:
    value = signature.strip()
    lower = value.lower()
    if lower.startswith("sha256="):
        return value.split("=", 1)[1].strip()
    return value


def _compute_expected_signatures(secret: str, timestamp: str, body: bytes) -> tuple[str, str]:
    payload = timestamp.encode("utf-8") + body
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    expected_hex = digest.hex()
    expected_b64 = base64.b64encode(digest).decode("ascii")
    return expected_hex, expected_b64


def _signature_matches(signature: str, expected_hex: str, expected_b64: str) -> bool:
    candidate = _strip_signature_prefix(signature)
    if not candidate:
        return False
    return hmac.compare_digest(candidate, expected_b64) or hmac.compare_digest(
        candidate.lower(), expected_hex.lower()
    )


@router.post("/zendesk")
async def zendesk_webhook(request: Request):
    settings = get_settings()
    body = await request.body()

    secret = settings.ZENDESK_WEBHOOK_SECRET
    if secret:
        logger.info(
            "Zendesk webhook signature validation start",
            extra={
                "candidates": settings.SIGNATURE_HEADER_CANDIDATES,
                "content_length": len(body),
            },
        )
        signature_entry = _extract_signature(request.headers, settings.SIGNATURE_HEADER_CANDIDATES)
        if not signature_entry:
            logger.warning(
                "Missing Zendesk signature header",
                extra={"candidates": settings.SIGNATURE_HEADER_CANDIDATES},
            )
            raise HTTPException(status_code=401, detail="Missing signature")
        header_name, signature_value = signature_entry
        timestamp = request.headers.get(settings.SIGNATURE_TIMESTAMP_HEADER)
        if not timestamp:
            logger.warning(
                "Missing Zendesk signature timestamp header",
                extra={"header": settings.SIGNATURE_TIMESTAMP_HEADER},
            )
            raise HTTPException(status_code=401, detail="Missing signature timestamp")
        expected_hex, expected_b64 = _compute_expected_signatures(secret, timestamp, body)
        if settings.ENV.lower() == "dev":
            # Local-only signature tracing to validate integration during development.
            logger.debug(
                "Zendesk webhook signature debug",
                extra={
                    "header": header_name,
                    "received_signature": signature_value,
                    "computed_signature_hex": expected_hex,
                    "computed_signature_b64": expected_b64,
                },
            )
        is_valid = _signature_matches(signature_value, expected_hex, expected_b64)
        if settings.ENV.lower() == "dev":
            logger.debug(
                "Zendesk webhook signature validation",
                extra={"header": header_name, "valid": is_valid},
            )
        if not is_valid:
            logger.warning(
                "Invalid Zendesk signature",
                extra={
                    "header": header_name,
                    "content_length": len(body),
                    "signature_length": len(signature_value),
                },
            )
            raise HTTPException(status_code=401, detail="Invalid signature")
        logger.info(
            "Zendesk webhook signature valid",
            extra={"header": header_name, "content_length": len(body)},
        )
    else:
        logger.info(
            "Zendesk webhook signature validation skipped",
            extra={"reason": "missing_secret", "content_length": len(body)},
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON payload", extra={"content_length": len(body)})
        raise HTTPException(status_code=400, detail="Invalid JSON")

    result = await event_router.process_zendesk_event(payload)
    if not result.get("ok"):
        return JSONResponse(status_code=500, content=result)
    return result
