from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

from fastapi.concurrency import run_in_threadpool

from app import config, rules, slack, storage, zendesk
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_str_list(value: Any) -> list[str] | None:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [str(item).strip() for item in value if str(item).strip()]
    return None


async def process_zendesk_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    dedupe_key = ""
    decision_dict: Dict[str, Any] | None = None
    slack_sent = False
    zendesk_updated = False
    zendesk_dry_run = settings.ZENDESK_DRY_RUN

    try:
        dedupe_key = storage.make_dedupe_key(payload)
        logger.info("Idempotency check", extra={"dedupe_key": dedupe_key})
        if not await run_in_threadpool(storage.try_register_event, dedupe_key, payload):
            logger.info(
                "Idempotency skip: duplicate event",
                extra={"dedupe_key": dedupe_key},
            )
            return {"ok": True, "skipped": True, "dedupe_key": dedupe_key}

        decision = rules.evaluate(payload)
        route_cfg = config.get_route_config(decision.route_to)

        group_id = _safe_int(route_cfg.get("group_id"))
        assignee_id = _safe_int(route_cfg.get("assignee_id"))
        slack_channel = _safe_str(route_cfg.get("slack_channel"))
        notify_on = _safe_str_list(route_cfg.get("notify_on"))

        notify = decision.notify
        if notify_on is not None:
            notify = decision.severity in notify_on
        if settings.DEBUG_FORCE_NOTIFY and not notify:
            logger.info(
                "Debug force notify enabled",
                extra={"dedupe_key": dedupe_key, "reason": decision.reason},
            )
            notify = True

        decision_dict = {
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
        logger.info(
            "Rules evaluation complete",
            extra={
                "dedupe_key": dedupe_key,
                "route_to": decision.route_to,
                "severity": decision.severity,
                "notify": notify,
                "reason": decision.reason,
                "tags": decision.tags,
                "group_id": group_id,
                "assignee_id": assignee_id,
                "slack_channel": slack_channel,
                "notify_on": notify_on,
            },
        )

        try:
            await run_in_threadpool(storage.save_decision, dedupe_key, payload, decision_dict)
        except Exception as exc:
            logger.exception("Failed to save decision: %s", exc)

        ticket_id = _safe_int(payload.get("ticket_id"))
        has_notification = await run_in_threadpool(storage.has_notification, "slack", dedupe_key)
        slack_enqueued = False
        slack_skip_reason = None
        if notify and not has_notification:
            try:
                slack_enqueued = True
                logger.info(
                    "Slack notification sending",
                    extra={
                        "dedupe_key": dedupe_key,
                        "slack_channel": slack_channel,
                    },
                )
                await slack.send_decision_alert(decision_dict, payload)
                slack_sent = True
                logger.info(
                    "Slack notification sent",
                    extra={"dedupe_key": dedupe_key, "slack_channel": slack_channel},
                )
                await run_in_threadpool(
                    storage.mark_notification,
                    "slack",
                    dedupe_key,
                    ticket_id,
                )
            except Exception as exc:
                logger.exception("Slack notification failed: %s", exc)
        else:
            slack_skip_reason = "notify_false" if not notify else "already_notified"
            logger.info(
                "Slack notification skipped",
                extra={
                    "dedupe_key": dedupe_key,
                    "reason": slack_skip_reason,
                },
            )
        logger.info(
            "Slack notification decision",
            extra={
                "ticket_id": ticket_id,
                "route_to": decision.route_to,
                "severity": decision.severity,
                "notify": notify,
                "slack_enqueued": slack_enqueued,
                "slack_skip_reason": slack_skip_reason,
            },
        )

        if ticket_id is None:
            logger.info(
                "Zendesk update skipped",
                extra={"dedupe_key": dedupe_key, "reason": "missing_ticket_id"},
            )
        elif not (group_id is not None or assignee_id is not None or decision.tags):
            logger.info(
                "Zendesk update skipped",
                extra={"dedupe_key": dedupe_key, "reason": "no_updates"},
            )
        else:
            if zendesk_dry_run:
                logger.info(
                    "Zendesk update skipped: dry run",
                    extra={
                        "dedupe_key": dedupe_key,
                        "ticket_id": ticket_id,
                        "group_id": group_id,
                        "assignee_id": assignee_id,
                        "tags": decision.tags,
                    },
                )
                zendesk_updated = False
            else:
                try:
                    update_payload = zendesk.build_ticket_update_payload(
                        tags=decision.tags,
                        comment=(
                            f"Auto-routing: {decision.reason}\n"
                            f"Route: {decision.route_to}\n"
                            f"Severity: {decision.severity}"
                        ),
                        assignee_id=assignee_id,
                        group_id=group_id,
                        add_internal_comment=settings.ZENDESK_ADD_INTERNAL_COMMENT,
                    )
                    logger.info(
                        "Zendesk update sending",
                        extra={
                            "dedupe_key": dedupe_key,
                            "ticket_id": ticket_id,
                            "group_id": group_id,
                            "assignee_id": assignee_id,
                            "tags": decision.tags,
                        },
                    )
                    logger.debug(
                        "Zendesk update payload",
                        extra={"ticket_id": ticket_id, "payload": update_payload},
                    )
                    result = await zendesk.update_ticket(
                        ticket_id, update_payload, dry_run=zendesk_dry_run
                    )
                    zendesk_updated = bool(result.get("ok"))
                except Exception as exc:
                    logger.exception("Zendesk update failed: %s", exc)

        return {
            "ok": True,
            "dedupe_key": dedupe_key,
            "decision": decision_dict,
            "slack_sent": slack_sent,
            "zendesk_updated": zendesk_updated,
            "zendesk_dry_run": zendesk_dry_run,
        }
    except Exception as exc:
        logger.exception("Unhandled error: %s", exc)
        return {
            "ok": False,
            "dedupe_key": dedupe_key,
            "decision": decision_dict,
            "slack_sent": slack_sent,
            "zendesk_updated": zendesk_updated,
            "zendesk_dry_run": zendesk_dry_run,
            "error": str(exc),
        }
