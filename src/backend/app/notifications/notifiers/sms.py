import httpx
import string

from ..base import Notifier, post
from ..models import DeliveryResult


class SMSNotifier(Notifier):
    async def send(self, event, config):
        # ASCII avoids UCS-2's 70-character billing segments; preserve an intact link
        # when it fits, otherwise omit it instead of sending a broken URL.
        link = event.dashboard_link if len(event.dashboard_link) <= 100 else ""
        summary = f"{event.new_severity} {event.instance}: {event.description}".replace("\n", "; ")
        # Use only single-septet GSM characters in the summary. URL extension
        # characters use two septets; account for those without altering the URL.
        allowed = set(string.ascii_letters + string.digits + " .,:;!?@#$%&()*+-/=_<>\"'")
        summary = "".join(c if c in allowed else "?" for c in summary)
        extension = set("^{}\\[~]|€")
        if any(c not in allowed | extension for c in link):
            link = ""
        link_size = sum(2 if c in extension else 1 for c in link)
        text = summary[:160 - link_size - (1 if link else 0)] + (" " + link if link else "")
        results = []
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            for number in config["to_numbers"]:
                results.append(await post(client, f'https://api.twilio.com/2010-04-01/Accounts/{config["account_sid"]}/Messages.json',
                                          auth=(config["account_sid"], config["auth_token"]),
                                          data={"From": config["from_number"], "To": number, "Body": text}))
        if all(r.ok for r in results):
            return DeliveryResult(ok=True, attempts=max(r.attempts for r in results))
        # Per-recipient HTTP retries happen above. Never resend successful recipients.
        return DeliveryResult(ok=False, message="SMS delivery failed for one or more recipients",
                              attempts=max(r.attempts for r in results))
