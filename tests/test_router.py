import asyncio
import json

from app import router, storage


def test_router_pipeline_dry_run(monkeypatch, tmp_path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps({"finance": {"group_id": 123}}), encoding="utf-8")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MAPPING_PATH", str(mapping_path))
    monkeypatch.setenv("ZENDESK_DRY_RUN", "true")

    payload = {"ticket_id": 123, "type": "billing", "priority": "low"}
    result = asyncio.run(router.process_zendesk_event(payload))

    assert result["ok"] is True
    assert result["decision"]["route_to"] == "finance"
    assert result["zendesk_dry_run"] is True
    assert result["slack_sent"] is False

    decisions = storage.fetch_recent_decisions(1)
    assert decisions
