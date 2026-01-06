import base64
import hashlib
import hmac

from fastapi.testclient import TestClient

from app.main import app
from app import webhook


def test_webhook_signature_valid(monkeypatch, tmp_path):
    secret = "testsecret"
    monkeypatch.setenv("ZENDESK_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MAPPING_PATH", str(tmp_path / "mapping.json"))

    async def fake_process(payload):
        return {"ok": True, "payload": payload}

    monkeypatch.setattr(webhook.event_router, "process_zendesk_event", fake_process)

    body = b'{"ticket_id":123,"type":"billing","priority":"low"}'
    timestamp = "1700000000"
    payload = timestamp.encode("utf-8") + body
    signature = base64.b64encode(
        hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    ).decode("ascii")

    client = TestClient(app)
    response = client.post(
        "/webhooks/zendesk",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Zendesk-Webhook-Signature": signature,
            "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_webhook_signature_invalid(monkeypatch, tmp_path):
    secret = "testsecret"
    monkeypatch.setenv("ZENDESK_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MAPPING_PATH", str(tmp_path / "mapping.json"))

    async def fake_process(payload):
        return {"ok": True, "payload": payload}

    monkeypatch.setattr(webhook.event_router, "process_zendesk_event", fake_process)

    body = b'{"ticket_id":123,"type":"billing","priority":"low"}'
    client = TestClient(app)
    response = client.post(
        "/webhooks/zendesk",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Zendesk-Webhook-Signature": "deadbeef",
            "X-Zendesk-Webhook-Signature-Timestamp": "1700000000",
        },
    )
    assert response.status_code == 401
