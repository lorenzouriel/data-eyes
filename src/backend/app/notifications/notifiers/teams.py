import httpx

from ..base import Notifier, post


class TeamsNotifier(Notifier):
    async def send(self, event, config):
        card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.2",
                "body": [{"type": "TextBlock", "weight": "Bolder", "wrap": True,
                          "color": {"CRITICAL": "Attention", "WARNING": "Warning", "OK": "Good"}.get(event.new_severity, "Default"),
                          "text": f"[{event.new_severity}] {event.instance}"},
                         {"type": "TextBlock", "wrap": True, "text": event.description[:10000]}],
                "actions": [{"type": "Action.OpenUrl", "title": "Open in Data Eyes", "url": event.dashboard_link}]}
        payload = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]}
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            return await post(client, config["webhook_url"], json=payload)
