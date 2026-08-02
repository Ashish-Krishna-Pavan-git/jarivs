# Reports & Daily Digest

JARVIS generates structured intelligence reports automatically on a schedule and makes them available through the Reports page of the dashboard.

---

## Report Types

### Cycle Digests

Generated after every intelligence collection cycle (08:00, 15:00, and 21:00 IST by default).

Each cycle digest is an AI-synthesized summary of all articles processed in that cycle. The digest includes:

- **Headline** — one-line summary of the cycle's main theme
- **Cybersecurity updates** — top security events, attacks, and vulnerabilities
- **AI/ML updates** — notable AI model releases, research, and tools
- **Tech & business updates** — product launches, acquisitions, policy changes
- **Hardware & mobile updates** — hardware releases and mobile platform news
- **CVE list** — vulnerability IDs mentioned across the cycle's articles
- **Strategic note** — analyst-level commentary on trends and patterns

Cycle digests are saved to `$JARVIS_DATA_DIR/daily/` as JSON files with a timestamp.

### Daily Executive Summary

Generated every morning at 07:00 IST.

The daily summary synthesizes all cycle digests from the past 24 hours into a higher-level executive briefing:

- **Day headline** — single-sentence summary of the day
- **Risk level** — `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` overall day risk
- **Executive summary** — two to three paragraph narrative
- **Escalating threats** — threats that intensified over the day
- **New patterns** — emerging trends or threat actor pivots observed
- **Actor activity** — named threat group or APT activity
- **Critical CVEs** — highest-priority vulnerabilities
- **Tech trends** — AI, hardware, and technology highlights
- **Recommendations** — concrete next steps for security teams

The daily summary is delivered via:
1. **Telegram** — text message to configured channels
2. **Audio podcast** — text-to-speech MP3 sent to Telegram
3. **WordPress** — formatted HTML post published to your site

### Sunday Weekly Edition (Doom vs Bloom)

Runs automatically every Sunday alongside the daily summary.

Synthesizes the past 7 days of articles into a "Doom vs Bloom" format:
- **Doom** — the most significant threat escalations of the week
- **Bloom** — positive developments, patches, and good news

Delivered as Telegram message + audio + WordPress post.

---

## Viewing Reports in the Dashboard

Reports are accessible at **User → Reports** (`/user/#reports`).

The Reports page shows:
- All saved cycle digests (newest first)
- Each digest's headline, cycle slot, and timestamp
- Expandable sections for all digest fields
- A "Download JSON" option for programmatic access

---

## Fallback Behavior (Degraded Mode)

If AI synthesis fails during a cycle (e.g., all API keys exhausted), JARVIS saves a **degraded digest** with:
- Top articles grouped by category (no AI narrative)
- A strategic note explaining that AI was unavailable
- The cycle number and processing timestamp

This ensures the Reports page always has real content even when AI is down. The admin Logs page shows the reason for the fallback.

---

## WordPress Publishing

The daily executive summary is published to WordPress if credentials are configured in `.env`.

See [WordPress Integration](wordpress.md) for full setup instructions.

The audit trail for all WordPress publish attempts is at `$JARVIS_DATA_DIR/wordpress_posts.jsonl`.

---

## File Layout

Reports and digests are stored in the JARVIS data directory (default `/data` in Docker):

```
$JARVIS_DATA_DIR/
├── daily/
│   ├── digest_YYYYMMDD_HHMMSS_cycle_N.json   # Cycle digests
│   └── daily_YYYY-MM-DD.json                  # Daily executive summary
├── archive/
│   └── ...                                    # Digests older than 3 days
└── wordpress_posts.jsonl                      # WordPress publish audit log
```

The archive manager automatically moves files older than 3 days from `daily/` to `archive/` to keep the active directory lean.

---

## Triggering Reports Manually

From the **Admin → Testing** page:

| Button | Action |
|---|---|
| **Run Collection Cycle** | Runs a full collection + AI processing + digest save |
| **Run Daily Summary** | Runs the 07:00 morning pipeline (Telegram + audio + WordPress) |
| **Run Weekly Summary** | Runs the Sunday Doom vs Bloom pipeline |

---

## Scheduler Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `DAILY_SUMMARY_HOUR` | `7` | Hour (IST) to run the daily summary (0–23) |
| `CYCLE_HOURS` | `8` | Not used directly — cycle slots are hardcoded at 08:00/15:00/21:00 |

Cycle times are hardcoded at 08:00, 15:00, and 21:00 IST to avoid data duplication from frequent re-processing. Change the `CYCLE_SLOTS` list in `backend/scheduler/scheduler.py` if you need different times.
