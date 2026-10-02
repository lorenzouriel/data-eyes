from email.message import EmailMessage
from html import escape

import aiosmtplib

from ..base import Notifier
from ..models import DeliveryResult


class EmailNotifier(Notifier):
    async def send(self, event, config):
        message = EmailMessage()
        category = "Health digest" if event.grouped else event.category
        message["Subject"] = f"[{event.new_severity}] {event.instance} — {category}".replace("\r", " ").replace("\n", " ")[:200]
        message["From"] = config["from_addr"]
        message["To"] = ", ".join(config["to_addrs"])
        message.set_content(f"{event.instance}\n{event.description}\n{event.dashboard_link}\n{event.timestamp.isoformat()}")
        message.add_alternative(f"<h2>{escape(event.instance)}</h2><pre>{escape(event.description)}</pre>"
                                f'<p><a href="{escape(event.dashboard_link, quote=True)}">Open in Data Eyes</a></p>', subtype="html")
        port = config.get("port", 587)
        tls = config.get("use_tls", True)
        try:
            refused, _ = await aiosmtplib.send(message, hostname=config["smtp_host"], port=port,
                                             username=config.get("username") or None, password=config.get("password") or None,
                                             use_tls=tls and port == 465, start_tls=tls and port != 465, timeout=15)
            if refused:
                # Retrying the entire list would duplicate successful recipients.
                return DeliveryResult(ok=False, message="Some email recipients were refused")
            return DeliveryResult(ok=True)
        except aiosmtplib.SMTPResponseException as exc:
            return DeliveryResult(ok=False, message=f"SMTP error {exc.code}", retryable=400 <= exc.code < 500)
        except (aiosmtplib.SMTPException, OSError):
            return DeliveryResult(ok=False, message="SMTP connection failed", retryable=True)
