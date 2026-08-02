# Integrations

JARVIS integrates with external services for notifications and publishing.

---

## Telegram

### Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram.
2. Copy the bot token.
3. Set `TELEGRAM_TOKEN` in `.env`.
4. Message your bot: `/start`

The bot registers your chat ID as an enabled notification channel. To unsubscribe, send `/stop`.

### What gets sent

| Event | Trigger |
|---|---|
| **Immediate alert** | Article flagged `CRITICAL` or `HIGH` severity during processing |
| **Cycle digest** | End of each collection cycle (08:00, 15:00, 21:00 IST) |
| **Daily summary** | Each morning at 07:00 IST |
| **Audio podcast** | After the daily summary — MP3 file |
| **Weekly edition** | Every Sunday — Doom vs Bloom briefing |
| **Startup message** | When JARVIS restarts |

### Multiple recipients

JARVIS supports multiple Telegram chat IDs simultaneously. Users can add their own chat ID through **User → Preferences → Notification Channels**. Admins manage all channels from **Admin → Integrations**.

---

## Slack

### Setup

1. Create a Slack app at [api.slack.com](https://api.slack.com/apps).
2. Enable **Incoming Webhooks** and add a new webhook for a channel.
3. Copy the webhook URL.
4. Set `SLACK_WEBHOOK_URL` in `.env`, or add it in **Admin → Integrations → Slack**.

Slack receives the same alerts as Telegram. Multiple Slack workspace webhooks are supported.

---

## WordPress

### Setup

Publish the daily AI intelligence report automatically to your WordPress site.

See the full [WordPress Integration Guide](wordpress.md) for step-by-step setup.

**Environment variables required:**

```env
WP_URL=https://your-site.com
WP_USER=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_CATEGORY_ID=1
WP_POST_STATUS=publish
WP_TAGS=
```

### What gets published

- **Daily report**: every morning at 07:00 IST
- **Sunday weekly edition**: Doom vs Bloom (every Sunday)
- Rich HTML with dark-tech CSS, severity badges, CVE tags, and source links
- Duplicate-safe: JARVIS updates an existing post if one already exists for the same date

---

## HuggingFace Spaces (Remote Storage)

JARVIS can sync its runtime state (seen articles, digest state, telemetry) to a HuggingFace Dataset repository. This allows state to survive across container restarts on HuggingFace Spaces.

```env
HF_TOKEN=your_hf_token
HF_STORAGE_REPO=username/jarvis-data
```

Leave both empty to disable HF sync (recommended for local and Docker deployments where the volume persists).

---

## Ollama (Local AI)

Use a locally running Ollama instance as an AI provider instead of (or alongside) cloud APIs.

```env
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=phi4-mini
```

Pull the model before starting JARVIS:

```bash
ollama pull phi4-mini
```

Ollama is used as a fallback tier after Gemini and Groq. It can also be configured as a custom model provider from **Admin → Models**.

---

## MCP Servers (Tool Calling)

JARVIS supports the **Model Context Protocol (MCP)** for giving AI models access to external tools and data sources.

Configure MCP servers from **Admin → MCP**. JARVIS connects to stdio and HTTP MCP servers, runs tool calls, and incorporates the results into AI analysis.

See [MCP Guide](MCP.md) for details.
