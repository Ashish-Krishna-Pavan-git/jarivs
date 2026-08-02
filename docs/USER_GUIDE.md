# User Guide

## Signing in

Open `http://localhost:7860`. On a fresh installation, use `admin` and `admin123!ChangeMe`, then replace that temporary password. Accounts created by an administrator also require a password change on their first login.

## Intelligence feed

Open User -> Feed to see recently processed articles. Pick a time window, search by source, title, severity, CVE, actor, or tag, then open an item title to visit its original source. The feed combines new runtime output with detected legacy articles without rewriting the legacy files.

## Reports

Open User -> Reports for current cycle digests, daily summaries, and compatible digests found in legacy `jarvis-data/`. Reports are created by scheduled runs or an administrator's manual cycle.

## Built-in assistant

User -> Assistant answers operational questions such as:

- `How do I connect Telegram?`
- `Why did my MCP test fail?`
- `What does the storage page mean?`
- `Summarize recent high severity intelligence.`

It uses the local JARVIS guides and recent intelligence as context. When no AI provider is configured, it returns a safe built-in usage answer.

## Notifications

Open User -> Notifications to add your own delivery channels. A Telegram channel needs a chat ID; a Slack channel needs an Incoming Webhook URL. Your channel remains active until you disable it.

Telegram users can instead message the configured bot with `/start`. JARVIS stores that chat as an enabled channel. Send `/stop` to disable it.

## Preferences

Open User -> Preferences to save an account-level display theme and digest window. The theme switcher in the sidebar changes the console immediately; preferences are stored for later use.

## Getting help

Use the Assistant first, then review [Troubleshooting](TROUBLESHOOTING.md). An administrator can inspect the system log in Admin -> Logs.
