# Notifications

Administrators can open **Notifications** in the top navigation to configure
Slack, Teams Workflows, SMTP email, and Twilio SMS channels, rules, and test sends.
Channel configuration is encrypted with `INSTANCE_SECRET_KEY`. Back up this key
with the repository database; changing it makes stored credentials unreadable.
Secrets are masked in API responses and preserved when left blank during editing.

Set `PUBLIC_BASE_URL` in `src/backend/.env` to the dashboard's externally reachable
origin (including any deployment prefix), and optionally set
`NOTIFICATION_COOLDOWN_SECONDS` (default 900). A rule can override the cooldown,
including zero. Restart the backend after changing environment settings.

The backend automatically runs `app/notification_schema.sql` at startup to add
the four notification tables to existing repositories. Fresh databases also get
the tables from `src/repository/init.sql`. No manual data migration is needed.

## Delivery behavior

- The first observation of each instance/category establishes its baseline.
  Subsequent severity changes are evaluated at the end of each collector cycle.
  Unchanged or older observations do not send messages.
- Instance and category filters are exact matches; blank matches all. `overall`
  is a separate category. A rule matching all categories can include both overall
  and individual category transitions.
- Recovery is an opt-in transition from WARNING/CRITICAL to OK. It follows the
  same cooldown and quiet hours as other alerts. UNKNOWN to OK is not recovery.
- Quiet hours are UTC, start inclusive and end exclusive, and may cross midnight.
  Suppressed transitions are logged and are not replayed after quiet hours or
  cooldown expire. Cooldowns are per rule, instance, and category; grouped rules
  use a single cooldown per instance. Overlapping rules deliver independently.
- Grouping combines a rule's matching transitions for one instance into one
  message per cycle. It also provides the optional per-instance email digest.
- State changes and outbox records are committed atomically. Database locks and
  delivery leases coordinate concurrent workers. Attempts survive restarts;
  transient HTTP failures retry up to three times with bounded delays and honor
  Retry-After. Longer delays defer to a later collector cycle. Queue delivery
  rounds are capped at three; exhausted deliveries remain visible as failed.
- Delivery is at least once: a crash after a provider accepts a message but
  before the result is saved can cause a duplicate. SMTP/SMS partial-recipient
  failures are not retried as a whole, to avoid resending to successful recipients.
- Disabling/deleting a channel prevents queued deliveries when next claimed.
  Deleting a channel also deletes its rules; historical log entries remain.
  Log entries are immutable except for deleting completed entries. Queued and
  in-flight entries cannot be deleted. The displayed attempts count is delivery
  rounds (test records show transport attempts).

## Channel setup

**Slack:** Supply an incoming webhook URL; mention and channel are optional.
Modern Slack incoming webhooks use the channel selected when the webhook was
installed and can ignore an explicit channel override. Messages use Block Kit
inside a colored attachment. See [Slack's webhook documentation](https://api.slack.com/messaging/webhooks).

**Teams:** Supply a Teams Workflows webhook configured to accept incoming webhook
requests and post Adaptive Cards. The workflow must permit the request's
authentication mode (this integration sends the webhook URL without a separate
Microsoft identity token). See [Microsoft's webhook documentation](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook).

**Email:** Supply host, port, sender and recipients, and optional SMTP credentials.
With TLS enabled, port 465 uses implicit TLS; other ports require STARTTLS.
With TLS disabled, SMTP is plaintext. Both HTML and plain-text bodies are sent.
See [aiosmtplib's send documentation](https://aiosmtplib.readthedocs.io/en/stable/reference.html).

**SMS:** Supply Twilio account SID, auth token, sender and E.164 recipients
(for example `+15551234567`). Rules default to CRITICAL-only and recovery off;
tests send real billable SMS. Messages are capped at 160 characters, using ASCII
text. A dashboard link is retained when it fits, and omitted when too long;
no external URL shortening service receives dashboard addresses. See
[Twilio's Messages API](https://www.twilio.com/docs/messaging/api/message-resource).

## Checks

From `src/backend`, run `uv run pytest -p no:cacheprovider`. Tests mock HTTP and
SMTP so they never send notifications. Optional PostgreSQL tests use only an
explicit disposable database named `data_eyes_notification_test`, configured
through `NOTIFICATION_TEST_POSTGRES_DSN`. From `src/frontend`, run `npm run build`.
