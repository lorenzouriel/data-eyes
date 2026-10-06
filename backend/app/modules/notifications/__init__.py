"""Notification channel registry."""
from app.modules.notifications.notifiers.email import EmailNotifier
from app.modules.notifications.notifiers.slack import SlackNotifier
from app.modules.notifications.notifiers.sms import SMSNotifier
from app.modules.notifications.notifiers.teams import TeamsNotifier

REGISTRY = {"slack": SlackNotifier, "teams": TeamsNotifier, "email": EmailNotifier, "sms": SMSNotifier}
