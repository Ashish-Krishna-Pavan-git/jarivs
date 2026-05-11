# JARVIS — Complete Fix Guide

## What Was Broken & What Was Fixed

| # | Bug | Impact | Fix |
|---|-----|--------|-----|
| 1 | Telegram timeout = 20s | No alerts/digests delivered | Raised to 60s + 3 retries with backoff |
| 2 | Deep dive returns raw JSON | Unreadable dossiers | `local_call_text()` — plain markdown mode |
| 3 | `FORCE_TEST_WEEKLY = True` hardcoded | Weekly ran EVERY day | Changed to `False` |
| 4 | Global AI rate lock blocks bot thread | `/quiz` and `/deepdive` froze during cycles | Per-API locks (Gemini lock, Groq lock) |
| 5 | No HF persistence | Data wiped on restart | `storage_backend.py` syncs to HF Dataset |
| 6 | `telemetry.py` self-reference bug | Crash on missing telemetry.json | Fixed `_default()` function |
| 7 | `seen.json` grows forever | Eventually slows dedup | Auto-prune to 30,000 entries |
| 8 | Queue written to disk per operation | Slow for 200-1200 articles | Pure in-memory queue |

---

## Step 1: Add HF Space Secrets

Go to your HF Space → **Settings → Variables and Secrets**

Add these secrets:

```
GEMINI_API_KEY      = your Gemini key
GROQ_API_KEY        = your Groq key
TELEGRAM_TOKEN      = your bot token
TELEGRAM_CHAT_ID    = your chat ID
WP_URL              = https://akpghub.live
WP_USER             = your WP username
WP_APP_PASSWORD     = your WP app password

# NEW — for persistence across restarts:
HF_TOKEN            = hf_xxxxxxxxxxxx   ← Your HF write token (Settings → Access Tokens)
HF_STORAGE_REPO     = AKP-07/jarvis-data  ← Create this dataset repo first (see Step 2)
```

---

## Step 2: Create the HF Dataset Repo (one time only)

1. Go to https://huggingface.co/new-dataset
2. Set name: `jarvis-data`
3. Set visibility: **Private**
4. Click **Create**

The repo will be at: `AKP-07/jarvis-data`

That's it. JARVIS will auto-create files in it.

---

## Step 3: Add to requirements.txt

Make sure these are in your `requirements.txt`:

```
flask
feedparser
requests
python-dotenv
google-genai
groq
beautifulsoup4
huggingface_hub   ← ADD THIS (for HF Dataset persistence)
edge-tts          ← for audio podcast (optional)
python-wordpress-xmlrpc
```

---

## Step 4: Replace Files

Replace ALL of these files in your HF Space:

| File | Status |
|------|--------|
| `storage_backend.py` | **NEW** — must add |
| `config.py` | Updated |
| `notifier.py` | Updated (critical fix) |
| `ai_router.py` | Updated (critical fix) |
| `bot_listener.py` | Updated (deepdive fix) |
| `queue_manager.py` | Updated |
| `storage.py` | Updated |
| `dedupe.py` | Updated |
| `telemetry.py` | Updated |
| `dailySummary.py` | Updated (critical fix) |
| `scheduler.py` | Updated |
| `worker_processor.py` | Updated |

Files you do NOT need to change:
- `scraper.py` ✓
- `collector.py` ✓
- `intelligence.py` ✓
- `archive_manager.py` ✓
- `audio_generator.py` ✓
- `internet_monitor.py` ✓
- `newsletter_publisher.py` ✓
- `app.py` ✓

---

## Step 5: Keep Space Awake (UptimeRobot)

HF Spaces can go to sleep. Set up a free pinger:

1. Go to https://uptimerobot.com (free account)
2. Add monitor → HTTP(s)
3. URL: `https://akp-07-jarvis-agent.hf.space/ping`
4. Interval: **5 minutes**

This pings your `/ping` endpoint so the space never sleeps.

---

## How HF Dataset Persistence Works

```
On Space startup:
  storage_backend.pull_state()
    → Downloads seen.json, digest_state.json, telemetry.json from HF Dataset
    → Restores dedup memory, cycle counter, stats

After every cycle:
  storage_backend.push_state(processed_articles=[...])
    → Uploads state files back to HF Dataset
    → Uploads a rolling 72-hour article bundle (for daily summary)

Result: Space restarts are transparent — JARVIS picks up exactly where it left off
```

---

## AI API Limits (Gemini Free Tier)

| Metric | Limit | Your Usage |
|--------|-------|------------|
| Requests/minute | 15 RPM | 1 per 4.5s = ~13 RPM ✓ |
| Requests/day | 1,500 RPD | 200 articles × 3 cycles = 600/day ✓ |
| Tokens/day | 1M TPD | Well within limits ✓ |

First run (500-1200 articles): at 4.5s/article = 37-90 minutes.
This is expected and fine — it's a one-time cost.
Subsequent cycles: 100-200 articles = 8-15 minutes. Fast.

---

## Testing Individual Features

**Test daily summary right now:**
In `scheduler.py`, temporarily set:
```python
TEST_MODE_DAILY = True
```
Then restart the space. It will run daily summary after the next cycle.
Set back to `False` after testing.

**Test weekly summary:**
```python
TEST_MODE_WEEKLY = True
```

**Test deep dive:**
Send `/deepdive Ransomware` to your bot. Should return formatted text now, not JSON.

---

## What Gets Sent & When

| Report | When | Contains |
|--------|------|----------|
| 🚨 Immediate Alert | When CRITICAL/HIGH + actively exploited + confidence ≥ 7 | Single article alert |
| 📰 8hr Digest | After every cycle (every 8h) | AI summary of all new articles |
| 🗓 Daily Report | 7 AM IST, once per day | Cross-cycle AI correlation + stats |
| 🗓️ Weekly Report | Every Sunday | "Doom vs Bloom" 7-day summary |
| 🎙️ Audio Podcast | With daily report | TTS podcast of daily summary |
| 📝 Newsletter | With daily report | WordPress published post |
