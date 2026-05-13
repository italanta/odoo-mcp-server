"""
Tests for the outbound communication safety guard.

These are the most critical tests in the entire repo.
If any of these fail, we risk sending unintended emails to clients.
"""

import pytest
from src.mcp.odoo.utils.safety import SafetyGuard, SafetyViolation, INTERNAL_NOTE_SUBTYPE_ID


@pytest.fixture
def guard():
    return SafetyGuard()


class TestBlockedModels:
    """Models that are entirely blocked from AI access."""

    @pytest.mark.parametrize("model", [
        "mail.mail",
        "mail.mass_mailing",
        "sms.sms",
        "sms.composer",
        "calendar.attendee",
        "mailing.mailing",
        "mailing.contact",
    ])
    def test_blocked_model_raises(self, guard, model):
        with pytest.raises(SafetyViolation, match="blocked"):
            guard.validate_write(model, "create", {})

    def test_safe_model_passes(self, guard):
        # crm.lead is safe for field writes
        guard.validate_write("crm.lead", "write", {"name": "test"})


class TestBlockedMethods:
    """Methods that trigger outbound communication."""

    @pytest.mark.parametrize("method", [
        "action_send_mail",
        "action_quotation_send",
        "action_invoice_sent",
        "message_subscribe",
        "message_unsubscribe",
        "action_send_sms",
        "action_send",
        "send_mail",
    ])
    def test_blocked_method_raises(self, guard, method):
        with pytest.raises(SafetyViolation, match="blocked"):
            guard.validate_write("crm.lead", method, {})

    def test_safe_method_passes(self, guard):
        guard.validate_write("crm.lead", "write", {"stage_id": 5})


class TestMessagePost:
    """The most critical test: message_post type validation."""

    # ── Odoo 19: comment + subtype_id=2 is the new safe internal note ──

    def test_comment_with_internal_subtype_id_allowed(self, guard):
        """Odoo 19: message_type='comment' + subtype_id=2 is internal only — safe."""
        guard.validate_message_post({
            "message_type": "comment",
            "body": "test",
            "subtype_id": INTERNAL_NOTE_SUBTYPE_ID,
        })

    def test_comment_without_subtype_blocked(self, guard):
        """Bare comment without internal subtype sends emails — MUST be blocked."""
        with pytest.raises(SafetyViolation, match="comment"):
            guard.validate_message_post({"message_type": "comment", "body": "test"})

    def test_comment_with_wrong_subtype_id_blocked(self, guard):
        """comment + non-internal subtype_id is dangerous — MUST be blocked."""
        with pytest.raises(SafetyViolation, match="comment"):
            guard.validate_message_post({
                "message_type": "comment",
                "body": "test",
                "subtype_id": 1,  # subtype 1 is "Discussions" — sends notifications
            })

    def test_comment_with_mt_note_xmlid_allowed(self, guard):
        """comment + subtype_xmlid='mail.mt_note' is also safe (Odoo 19 compat)."""
        guard.validate_message_post({
            "message_type": "comment",
            "body": "test",
            "subtype_xmlid": "mail.mt_note",
        })

    # ── Odoo 18 backward compatibility: message_type='note' ──

    def test_message_type_note_allowed(self, guard):
        """message_type='note' is internal only — safe (Odoo 18 pattern)."""
        guard.validate_message_post({"message_type": "note", "body": "test"})

    def test_message_type_note_with_bad_subtype_blocked(self, guard):
        """Even with type='note', a non-note subtype_xmlid must be blocked."""
        with pytest.raises(SafetyViolation, match="subtype"):
            guard.validate_message_post({
                "message_type": "note",
                "body": "test",
                "subtype_xmlid": "mail.mt_comment",
            })

    # ── Always blocked types ──

    def test_message_type_default_blocked(self, guard):
        """Odoo defaults to 'comment' if no type specified — MUST be blocked."""
        with pytest.raises(SafetyViolation, match="comment"):
            guard.validate_message_post({"body": "test"})

    def test_message_type_email_blocked(self, guard):
        with pytest.raises(SafetyViolation):
            guard.validate_message_post({"message_type": "email", "body": "test"})

    def test_message_type_sms_blocked(self, guard):
        with pytest.raises(SafetyViolation):
            guard.validate_message_post({"message_type": "sms", "body": "test"})

    def test_message_type_notification_blocked(self, guard):
        with pytest.raises(SafetyViolation):
            guard.validate_message_post({"message_type": "notification", "body": "test"})

    # ── partner_ids always blocked ──

    def test_partner_ids_blocked_with_note(self, guard):
        """Specifying partner_ids notifies those partners — blocked even with type='note'."""
        with pytest.raises(SafetyViolation, match="partner_ids"):
            guard.validate_message_post({
                "message_type": "note",
                "body": "test",
                "partner_ids": [1, 2, 3],
            })

    def test_partner_ids_blocked_with_comment_subtype(self, guard):
        """partner_ids blocked even with safe comment + subtype_id=2."""
        with pytest.raises(SafetyViolation, match="partner_ids"):
            guard.validate_message_post({
                "message_type": "comment",
                "body": "test",
                "subtype_id": INTERNAL_NOTE_SUBTYPE_ID,
                "partner_ids": [1, 2, 3],
            })


class TestCalendarEvents:
    """Calendar events with attendees send email invitations."""

    def test_calendar_with_attendees_blocked(self, guard):
        with pytest.raises(SafetyViolation, match="attendees"):
            guard.validate_write("calendar.event", "create", {
                "name": "Meeting",
                "partner_ids": [(6, 0, [1, 2])],
            })

    def test_calendar_without_attendees_allowed(self, guard):
        """Personal reminders without attendees are safe."""
        guard.validate_write("calendar.event", "create", {
            "name": "Block time",
            "start": "2026-03-15 10:00:00",
            "stop": "2026-03-15 11:00:00",
        })

    def test_calendar_with_attendee_ids_blocked(self, guard):
        with pytest.raises(SafetyViolation, match="attendees"):
            guard.validate_write("calendar.event", "write", {
                "attendee_ids": [(4, 1)],
            })


class TestIntegration:
    """Full validate_write flow."""

    def test_crm_field_update_safe(self, guard):
        guard.validate_write("crm.lead", "write", {"expected_revenue": 50000})

    def test_crm_message_post_odoo19_safe(self, guard):
        """Odoo 19 internal note via validate_write."""
        guard.validate_write("crm.lead", "message_post", {
            "body": "Updated from email scan",
            "message_type": "comment",
            "subtype_id": INTERNAL_NOTE_SUBTYPE_ID,
        })

    def test_crm_message_post_odoo18_safe(self, guard):
        """Odoo 18 internal note via validate_write."""
        guard.validate_write("crm.lead", "message_post", {
            "body": "Updated from email scan",
            "message_type": "note",
            "subtype_xmlid": "mail.mt_note",
        })

    def test_crm_message_post_comment_blocked(self, guard):
        with pytest.raises(SafetyViolation):
            guard.validate_write("crm.lead", "message_post", {
                "body": "This would email the client!",
                "message_type": "comment",
            })

    def test_knowledge_article_safe(self, guard):
        guard.validate_write("knowledge.article", "create", {
            "name": "Client overview",
            "body": "...",
        })

    def test_mail_activity_safe(self, guard):
        guard.validate_model_access("mail.activity", "create")

    def test_mail_mail_blocked(self, guard):
        with pytest.raises(SafetyViolation):
            guard.validate_model_access("mail.mail", "create")
