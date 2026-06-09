"""Outbound email infrastructure (SMTP)."""

from src.infrastructure.email.client import EmailSender, email_sender

__all__ = ["EmailSender", "email_sender"]
