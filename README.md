---
title: Jarvis Agent
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: true
license: mit
---

# JARVIS — Intelligence System

> Automated threat intelligence, AI analysis, and daily briefings delivered to Telegram.

Every 8 hours JARVIS collects articles from 30+ sources across cybersecurity, AI, tech, hardware, and mobile — analyses each one with AI, sends instant alerts for critical threats, and delivers structured intelligence digests to your Telegram channel. Every morning at 07:00 IST it sends a full daily report, audio podcast, and publishes a newsletter to WordPress.

---

## Schedule

| Time (IST) | Event |
|-----------|-------|
| 07:00 | Daily Report + Audio Podcast + WordPress Newsletter |
| 08:00 | Intelligence Cycle 1 |
| 15:00 | Intelligence Cycle 2 |
| 21:00 | Intelligence Cycle 3 |
| Sunday 07:00 | Weekly "Doom vs Bloom" Edition |

Immediate alerts fire any time a CRITICAL or HIGH severity article with active exploitation is detected.

---

## HF Space Secrets Required

Go to your Space → **Settings → Variables and Secrets** and add:

```
GEMINI_API_KEY      = your Gemini API key (free at aistudio.google.com)
GROQ_API_KEY        = your Groq API key   (free at console.groq.com)
TELEGRAM_TOKEN      = your bot token from @BotFather
TELEGRAM_CHAT_ID    = your personal chat ID
WP_URL              = https://yourdomain.com
WP_USER             = your WordPress username
WP_APP_PASSWORD     = WordPress Application Password
HF_TOKEN            = your HF write token (Settings → Access Tokens)
HF_STORAGE_REPO     = YourUsername/jarvis-data
```

Optional (for webhook mode — more reliable than polling):
```
HF_SPACE_URL        = https://your-space-name.hf.space
```

---

## One-Time Setup

### 1. Create HF Dataset for persistence
Go to https://huggingface.co/new-dataset  
Name: `jarvis-data` | Visibility: **Private** | Click Create  
Your repo will be at `YourUsername/jarvis-data` — add this to `HF_STORAGE_REPO`.

### 2. Get your Telegram credentials
1. Message `@BotFather` → `/newbot` → copy the token
2. Message your bot anything, then visit:  
   `https://api.telegram.org/bot<TOKEN>/getUpdates`  
   Find `chat.id` in the response — that's your `TELEGRAM_CHAT_ID`

### 3. Set up UptimeRobot (prevents Space sleeping)
1. Go to https://uptimerobot.com (free)
2. Add monitor → HTTP(s) → URL: `https://your-space.hf.space/ping`
3. Interval: **5 minutes**

This is required. HF Spaces sleep after 48h without external traffic.  
The scheduler also self-pings every 4 minutes as a backup.

### 4. WordPress Application Password
1. WordPress admin → Users → Profile → Application Passwords
2. Generate a new password → copy it to `WP_APP_PASSWORD`

---

## Files to Delete from Your Space

These files are not needed and should be removed:

| File | Reason |
|------|--------|
| `newslettertest.py` | Test script — not needed in production |
| `teletest.py` | Test script — not needed in production |
| `runtime_state.json` | Auto-generated at runtime — don't commit |
| `SETUP_AND_FIXES.md` | Outdated fix log — replaced by this README |
| `README_setup.md` | Replaced by this README |

---

## Bot Commands

Send these to your bot on Telegram:

| Command | Action |
|---------|--------|
| `/start` | Subscribe to alerts |
| `/stop` | Unsubscribe |
| `/status` | System health & stats |
| `/quiz` | Daily intelligence quiz |
| `/deepdive <topic>` | Full threat dossier on any topic |
| Any text | Ask JARVIS anything — general AI chat |

---

## AI Model Tiers

| Task | Primary | Fallback |
|------|---------|----------|
| Per-article analysis | Groq llama-3.1-8b (fast, 30 RPM) | Gemini 2.5 Flash |
| Cycle digest | Gemini 2.5 Flash (15 RPM) | Groq llama-3.3-70b |
| Daily/Weekly report | Gemini 2.5 Pro (best reasoning) | Flash → Groq 70b |
| Deepdive / Chat | Gemini 2.5 Flash | Groq llama-3.3-70b |

Gemini 2.5 Pro free tier: 25 RPD — used only for the 2-3 daily/weekly calls.

---

## Severity Routing

| Severity | Action |
|----------|--------|
| CRITICAL | Instant Telegram alert (if actively exploited + confidence ≥ 7) |
| HIGH | Instant alert (if urgent keywords + confidence ≥ 8) |
| MEDIUM | 8-hour digest only |
| LOW | 8-hour digest only |
| MINIMAL | Stored, not sent |

---

## Architecture

```
app.py          Flask web server + webhook handler + startup orchestrator
scheduler.py    Time-based cycle runner (08:00 / 15:00 / 21:00 IST)
collector.py    RSS feed fetcher (30+ sources)
scraper.py      Full article text extraction
dedupe.py       Fingerprint-based deduplication
worker_processor.py   AI analysis + alert routing per article
ai_router.py    Multi-tier model routing (Groq / Gemini)
notifier.py     Telegram broadcaster
bot_listener.py Telegram command + AI chat handler
dailySummary.py Morning pipeline: report + audio + newsletter
audio_generator.py    edge-tts podcast generation
newsletter_publisher.py  WordPress REST API publisher
storage.py      Local JSON/Markdown persistence
storage_backend.py    HF Dataset sync (survives restarts)
telemetry.py    Runtime statistics
runtime_state.py      Live cycle progress tracking
```

---

## Troubleshooting

**Bot not responding / 409 Conflict in logs**  
A stale webhook from a previous run is blocking polling.  
The fix is already in `app.py` — it calls `deleteWebhook` automatically before polling starts.  
If it persists: manually call `https://api.telegram.org/bot<TOKEN>/deleteWebhook`

**Daily report has no AI content (blank sections)**  
The cycle digest files in `/tmp/` were lost on Space restart.  
`dailySummary.py` now regenerates AI content directly from articles as a fallback.

**Audio not generating**  
Check edge-tts is installed: `pip install edge-tts`  
The generator uses the Python API (not shell commands) — should work on all platforms.

**Space sleeping despite UptimeRobot**  
Ensure the monitor is set to **5 minutes** interval and the URL is exactly `https://your-space.hf.space/ping`  
The scheduler also pings locally every 4 minutes as backup.

**Newsletter not publishing**  
Verify `WP_URL`, `WP_USER`, `WP_APP_PASSWORD` in Space secrets.  
Test by visiting `https://yourdomain.com/wp-json/wp/v2/posts` in a browser.
