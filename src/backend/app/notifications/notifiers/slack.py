import httpx

from ..base import Notifier, post


class SlackNotifier(Notifier):
    async def send(self, event, config):
        color = {"CRITICAL": "#dc2626", "WARNING": "#f59e0b", "OK": "#16a34a"}.get(event.new_severity, "#64748b")
        text = f"[{event.new_severity}] {event.instance}\n{event.description}"
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": text[:2900]}},
                  {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Open in Data Eyes"}, "url": event.dashboard_link}]}]
        if config.get("mention"):
            blocks.insert(0, {"type": "section", "text": {"type": "mrkdwn", "text": config["mention"][:1000]}})
        payload = {"text": text, "attachments": [{"color": color, "blocks": blocks}]}
        if config.get("channel"):
            payload["channel"] = config["channel"]
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            return await post(client, config["webhook_url"], json=payload)
