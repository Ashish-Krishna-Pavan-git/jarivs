# Backend Notifications Module

## Purpose
Delivers critical security alerts and cycle digests to Telegram bot chats and Slack webhooks.

## Contained Modules
- `notifier.py`: Telegram broadcaster with message splitting and exponential retry backoff.
- `slack_notifier.py`: Slack incoming webhook delivery module.
- `bot_listener.py`: Telegram interactive command listener.

## Dependencies
- `requests`, `backend.database.jarvis_db`, `backend.auth.security_utils`.

## Entry Points
- `send_telegram(msg)`: Broadcast message to Telegram chats.
- `send_slack(webhook, payload)`: Send payload to Slack webhook.

## Important Files
- [`notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/notifications/notifier.py)
- [`slack_notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/notifications/slack_notifier.py)
