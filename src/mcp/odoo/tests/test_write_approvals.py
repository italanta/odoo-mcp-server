import pytest

from src.mcp.odoo.utils.write_approvals import ApprovalStore, payload_hash


class TestPayloadHash:
    def test_hash_is_stable_across_key_order(self):
        left = {"model": "crm.lead", "values": {"name": "A", "stage_id": 3}}
        right = {"values": {"stage_id": 3, "name": "A"}, "model": "crm.lead"}

        assert payload_hash(left) == payload_hash(right)


class TestApprovalStore:
    def test_register_creates_unconsumed_record(self):
        store = ApprovalStore(ttl_seconds=60)

        record = store.register({"model": "crm.lead", "operation": "write"})

        assert record.token
        assert record.expires_at > record.created_at
        assert record.consumed is False

    def test_consume_marks_token_used(self):
        store = ApprovalStore(ttl_seconds=60)
        payload = {"model": "crm.lead", "operation": "write", "values": {"name": "A"}}
        record = store.register(payload)

        consumed = store.consume(record.token, payload)

        assert consumed.token == record.token
        assert consumed.consumed is True

        with pytest.raises(ValueError, match="already used"):
            store.consume(record.token, payload)

    def test_consume_rejects_unknown_token(self):
        store = ApprovalStore(ttl_seconds=60)

        with pytest.raises(ValueError, match="Unknown"):
            store.consume("missing", {"model": "crm.lead"})

    def test_consume_rejects_mismatched_payload(self):
        store = ApprovalStore(ttl_seconds=60)
        record = store.register({"model": "crm.lead", "operation": "write", "values": {"name": "A"}})

        with pytest.raises(ValueError, match="does not match"):
            store.consume(record.token, {"model": "crm.lead", "operation": "write", "values": {"name": "B"}})

    def test_consume_rejects_expired_token(self):
        store = ApprovalStore(ttl_seconds=60)
        payload = {"model": "crm.lead", "operation": "write", "values": {"name": "A"}}
        record = store.register(payload)
        store._records[record.token].expires_at = record.created_at - 1

        with pytest.raises(ValueError, match="expired"):
            store.consume(record.token, payload)
