import re

from app import storage


def test_make_dedupe_key_stable():
    payload = {
        "ticket_id": 123,
        "type": "billing",
        "priority": "low",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    key1 = storage.make_dedupe_key(payload)
    key2 = storage.make_dedupe_key(dict(payload))
    assert key1 == key2


def test_make_dedupe_key_hash_fallback():
    key = storage.make_dedupe_key({})
    assert re.fullmatch(r"[0-9a-f]{12}", key) is not None
