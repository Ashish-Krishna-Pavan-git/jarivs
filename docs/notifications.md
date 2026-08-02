# Notifications & Alerts System

JARVIS delivers real-time critical security alerts and cycle digests to Telegram chats and Slack webhooks.

## Architecture

- **Telegram Broadcaster ([`notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/notifier.py))**: Formats messages, splits long texts (>4000 chars), executes HTTP retries with exponential backoff (up to 5 retries), and posts audio podcast files (`send_audio`).
- **Slack Integrator ([`slack_notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/slack_notifier.py))**: Encrypts and manages Slack webhook URLs, broadcasting updates to configured webhooks.
- **Recipient Resolution**: Merges default environment channels (`TELEGRAM_CHAT_ID`, `SLACK_WEBHOOK_URL`) with user-defined notification channels in database (`notification_channels`).

---

## Immediate Alerting vs Digest Cycles

1. **Immediate Critical Alerts**:
   - Triggered automatically during worker item processing if an article is flagged as `CRITICAL` or `HIGH` severity with high confidence (>=7) and urgent indicators (e.g. active zero-day, unauthenticated RCE).
   - Suppressed by deduplication cooldown (`_on_cooldown`) if a similar alert was sent within 12 hours.

2. **Cycle Digests**:
   - Sent at the conclusion of each scheduled cycle (08:00, 15:00, 21:00 IST).
   - Summarizes top cybersecurity, AI, tech, and hardware stories with strategic analyst commentary.

---

## Inline Channel Testing

Notification channels can be tested directly from the UI:
- **Admin Channels**: `/admin/#integrations`
- **User Channels**: `/user/#notifications`
- **Command Center**: `/admin/#testing`

When the **Test** button is clicked, the backend calls `test_channel(kind, target, secret)` and returns inline status (`✓ Delivered` or error details).
