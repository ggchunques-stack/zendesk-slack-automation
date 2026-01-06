# Zendesk Automation MVP

Receives Zendesk webhook events, evaluates routing rules, sends Slack alerts for high/critical tickets, and optionally updates Zendesk tickets when not in dry-run.

## Quickstart

1) Create and activate a virtualenv.
2) Install dependencies:

```bash
pip install -r requirements.txt
```

3) Copy `.env.example` to `.env` and fill values, or export env vars directly.
4) Run the API:

```bash
uvicorn app.main:app --reload
```

5) Expose locally (ngrok):

```bash
ngrok http 8000
```

## Zendesk webhook/trigger payload

Configure a Zendesk webhook and trigger to POST JSON to:

```
https://<your-ngrok-subdomain>.ngrok.io/webhooks/zendesk
```

Include these fields in the payload (minimum for routing/dedupe):
- `ticket_id` (integer)
- `type` (category, e.g. "billing", "technical", "stream")
- `priority` (low/normal/high/urgent/critical)
- `updated_at` (timestamp, used for dedupe stability)
- `event_id` and/or `audit_id` (optional, improves dedupe)

## Dry-run vs real updates

- `ZENDESK_DRY_RUN=true`: Zendesk tickets are not updated; Slack notifications still send.
- `ZENDESK_DRY_RUN=false`: Zendesk ticket updates are executed when there are changes to apply.

## Debug endpoints

Debug endpoints are disabled unless `DEBUG_WEBHOOK_SIGNATURE=true`. When disabled, they return 404.

## Environment variables

Required for Zendesk API access (debug Zendesk calls, ticket updates):
- `ZENDESK_SUBDOMAIN`
- `ZENDESK_EMAIL`
- `ZENDESK_API_TOKEN`

Optional:
- `ENV` (default: `dev`)
- `SLACK_WEBHOOK_URL`
- `ZENDESK_WEBHOOK_SECRET` (enables signature validation)
- `ZENDESK_DRY_RUN` (default: `true`)
- `ZENDESK_ADD_INTERNAL_COMMENT` (default: `false`)
- `DEBUG_WEBHOOK_SIGNATURE` (default: `false`)
- `DEBUG_FORCE_NOTIFY` (default: `false`)
- `DATABASE_PATH` (default: `./data.db`)
- `MAPPING_PATH` (default: `./config/mapping.json`)
- `SIGNATURE_HEADER_CANDIDATES` (default: `X-Zendesk-Webhook-Signature,X-Zendesk-Signature,X-Hub-Signature-256`)
- `SIGNATURE_TIMESTAMP_HEADER` (default: `X-Zendesk-Webhook-Signature-Timestamp`)

## Webhook sanity check

Without signature:

```bash
curl -X POST http://localhost:8000/webhooks/zendesk \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":123,"type":"billing","priority":"low"}'
```

With signature (set `ZENDESK_WEBHOOK_SECRET`):

```bash
payload='{"ticket_id":123,"type":"billing","priority":"low"}'
timestamp="1700000000"
sig=$(python - <<'PY'
import base64, hashlib, hmac, os
body = b'{"ticket_id":123,"type":"billing","priority":"low"}'
timestamp = "1700000000"
secret = os.environ["ZENDESK_WEBHOOK_SECRET"].encode("utf-8")
payload = timestamp.encode("utf-8") + body
print(base64.b64encode(hmac.new(secret, payload, hashlib.sha256).digest()).decode("ascii"))
PY
)
curl -X POST http://localhost:8000/webhooks/zendesk \
  -H "Content-Type: application/json" \
  -H "X-Zendesk-Webhook-Signature: $sig" \
  -H "X-Zendesk-Webhook-Signature-Timestamp: $timestamp" \
  -d "$payload"
```
The webhook accepts base64 signatures (Zendesk) or hex signatures with an optional `sha256=` prefix.

## Debug endpoints
Debug endpoints are only enabled when `DEBUG_WEBHOOK_SIGNATURE=true`.

Zendesk calls:

```bash
curl http://localhost:8000/debug/zendesk/me
curl http://localhost:8000/debug/zendesk/tickets/123
```

Stored events/decisions:

```bash
curl "http://localhost:8000/debug/events/recent?limit=20"
curl "http://localhost:8000/debug/decisions/recent?limit=20"
curl "http://localhost:8000/debug/decisions/replay?ticket_id=123"
```

## Ngrok

Expose the webhook locally and set the Zendesk webhook URL to the public ngrok URL:

```bash
ngrok http 8000
```

## Testing

```bash
pytest
```

## Mapping configuration

The app reads `config/mapping.json` to determine how tickets are routed. The file is a JSON object keyed by `route_to`, where each value is a config object. Existing mappings that only include `group_id` remain valid.

Required per route:
- `group_id` (number)

Optional per route:
- `assignee_id` (number)
- `slack_channel` (string, e.g. "#support-alerts")
- `notify_on` (array of severities, e.g. ["high", "critical"]). When omitted, behavior is unchanged.

Example format:

```json
{
  "finance":   { "group_id": 123 },
  "stream_ops":{ "group_id": 456 },
  "support":   {
    "group_id": 789,
    "assignee_id": 555,
    "slack_channel": "#support-alerts",
    "notify_on": ["high", "critical"]
  }
}
```
