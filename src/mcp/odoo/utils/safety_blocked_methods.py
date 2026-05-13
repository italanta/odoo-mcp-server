"""Safety policy constants for blocked Odoo models/methods.

This module is the single source of truth for outbound-safety blocklists used
by SafetyGuard and related tests/docs.
"""

# BLOCKED: These operations send emails, SMS, or notifications to external
# parties. They must never be called by MCP tools.

BLOCKED_MODELS = frozenset({
    "mail.mail",  # Direct email sending
    "mail.mass_mailing",  # Mass email campaigns
    "mail.mass_mailing.contact",  # Mailing list management
    "sms.sms",  # SMS sending
    "sms.composer",  # SMS composition wizard
    "calendar.attendee",  # Calendar attendee management (sends invites)
    "mailing.mailing",  # Marketing automation
    "mailing.contact",  # Marketing contacts
})

BLOCKED_METHODS = frozenset({
    "unlink",  # Record deletion
    "action_send_mail",  # Quotation/Invoice email sending
    "action_quotation_send",  # Quotation email
    "action_invoice_sent",  # Invoice email
    "message_subscribe",  # Add followers (changes notification routing)
    "message_unsubscribe",  # Remove followers
    "action_send_sms",  # SMS sending
    "action_send",  # Generic send action
    "send_mail",  # Direct mail send
})

# message_post safety rules:
# - Odoo 18: message_type='note' was the safe internal type
# - Odoo 19: 'note' was removed. Safe internal notes now use
#   message_type='comment' + subtype_id=2 (internal "Note" subtype)
# - Bare 'comment' without subtype_id=2 still sends emails and is blocked
BLOCKED_MESSAGE_TYPES = frozenset({
    "email",  # Direct email
    "email_outgoing",  # Outgoing email
    "notification",  # Push notification
    "auto_comment",  # Automated targeted notification
    "user_notification",  # User specific notification
    "sms",  # SMS message
    "snailmail",  # Physical mail
})

SAFE_MESSAGE_TYPES = frozenset({
    "note",  # Internal log note (Odoo 18 backward compatibility)
})

# In Odoo 19, 'comment' is safe only when paired with the internal Note subtype.
INTERNAL_NOTE_SUBTYPE_ID = 2  # mail.message.subtype "Note" (internal=True)
