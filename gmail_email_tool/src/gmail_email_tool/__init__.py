"""Gmail email sending module."""

from gmail_email_tool.service import bootstrap_oauth, send_email

__all__ = ["bootstrap_oauth", "send_email"]

