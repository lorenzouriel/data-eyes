"""Notification channel registry."""
from .notifiers.email import EmailNotifier
from .notifiers.slack import SlackNotifier
from .notifiers.sms import SMSNotifier
from .notifiers.teams import TeamsNotifier

REGISTRY = {"slack": SlackNotifier, "teams": TeamsNotifier, "email": EmailNotifier, "sms": SMSNotifier}
