# WordPress Integration

JARVIS publishes the daily intelligence report to WordPress automatically at 07:00 IST using the WordPress REST API and **Application Passwords** — a secure built-in WordPress authentication mechanism that does not require your login password.

---

## How It Works

1. At 07:00 IST, the scheduler runs the daily report pipeline (`daily_summary.py`).
2. After generating the AI summary, it calls `newsletter_publisher.publish_to_wordpress()`.
3. JARVIS builds a dark-tech HTML report with severity badges, CVE tags, and source links.
4. It checks whether a post with today's slug already exists on WordPress.
   - If the post exists → **updates** it.
   - If the post doesn't exist → **creates** a new post.
5. The result (post ID, URL, action taken, any error) is written to the audit log at `$JARVIS_DATA_DIR/wordpress_posts.jsonl`.

---

## Setup

### Step 1 — Create a WordPress Application Password

1. Log into your WordPress admin panel.
2. Go to **Users → Profile** (or **Users → Your Profile**).
3. Scroll down to **Application Passwords**.
4. Enter a name (e.g. `JARVIS`) and click **Add New Application Password**.
5. Copy the generated password — it will look like `xxxx xxxx xxxx xxxx xxxx xxxx`.

> **Note**: Application Passwords require WordPress 5.6+ and HTTPS. If you are on HTTP only, you must enable Application Passwords explicitly via a plugin or filter.

### Step 2 — Set Environment Variables

Add these to your `.env` file:

```env
WP_URL=https://your-wordpress-site.com
WP_USER=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_CATEGORY_ID=1
WP_POST_STATUS=publish
WP_TAGS=
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `WP_URL` | ✅ Yes | — | Your WordPress site root URL (no trailing slash) |
| `WP_USER` | ✅ Yes | — | WordPress username (not email) |
| `WP_APP_PASSWORD` | ✅ Yes | — | Application Password from step 1 |
| `WP_CATEGORY_ID` | No | `1` | Category ID to assign the post |
| `WP_POST_STATUS` | No | `publish` | `publish` for live posts, `draft` to review before publishing |
| `WP_TAGS` | No | `""` | Comma-separated tag IDs to attach (e.g. `12,34,56`) |

### Step 3 — Restart JARVIS

```bash
docker compose restart
# or for local dev:
python app.py
```

JARVIS will automatically publish the next daily report to WordPress.

---

## Finding Your Category and Tag IDs

### Category IDs

In the WordPress admin panel, go to **Posts → Categories**. Hover over a category name — the URL in your browser status bar shows the term ID, e.g.:
```
https://yoursite.com/wp-admin/term.php?taxonomy=category&tag_ID=46&...
```
That `tag_ID=46` is your category ID.

Alternatively, use the WordPress REST API directly:

```bash
curl https://yoursite.com/wp-json/wp/v2/categories?per_page=50
```

### Tag IDs

Same approach via REST API:

```bash
curl https://yoursite.com/wp-json/wp/v2/tags?per_page=50
```

---

## Testing the Integration

You can trigger the WordPress publish step manually for testing from the **Admin → Testing → Command Center**:

1. Open `http://localhost:7860`.
2. Log in as admin.
3. Go to **Admin → Testing**.
4. Click **Run Daily Summary** under "Manual Pipeline Triggers".

Watch the backend logs for lines starting with `[WP]`:

```
[WP] ✓ Published new post (ID 1234): https://yoursite.com/jarvis-threat-intel-2026-08-02/
```

Or check the audit log:

```bash
cat $JARVIS_DATA_DIR/wordpress_posts.jsonl | python -m json.tool
```

---

## Post Format

Each published post includes:

- **Dark-tech CSS** (Orbitron + Inter fonts, sky-blue accents matching JARVIS theme)
- **Executive headline** with date and risk level badge
- **Executive summary** section
- **Escalating threats** list
- **Emerging patterns** list
- **Threat actor activity** section
- **CVE badges** with monospace styling
- **Tech & AI trends** list
- **Actionable recommendations** list
- **Top 10 source articles** by severity
- **Footer** with generation timestamp

---

## Duplicate Prevention

JARVIS generates a deterministic slug for each post:

```
jarvis-threat-intel-YYYY-MM-DD
```

Before publishing, it queries the WordPress REST API for an existing post with that slug. If found, the post is updated. This ensures no duplicate posts are created even if JARVIS restarts or the daily pipeline runs more than once.

---

## Audit Log

Every publish attempt is logged to:

```
$JARVIS_DATA_DIR/wordpress_posts.jsonl
```

Each line is a JSON object:

```json
{
  "slug": "jarvis-threat-intel-2026-08-02",
  "published_at": "2026-08-02T07:00:00.123456",
  "success": true,
  "action": "created",
  "post_id": 1234,
  "post_url": "https://yoursite.com/jarvis-threat-intel-2026-08-02/",
  "error": null
}
```

| Field | Values |
|---|---|
| `action` | `created`, `updated`, `skipped`, `error` |
| `success` | `true` / `false` |
| `error` | Error message string if `success` is `false`, otherwise `null` |

---

## Troubleshooting

### `[WP] WP_URL not set — skipping WordPress publish.`

Set `WP_URL` in your `.env` file and restart.

### `HTTP 401`

- Check that `WP_USER` is the WordPress **username** (not email address).
- Regenerate the Application Password — they expire if revoked.
- Verify your site uses HTTPS (Application Passwords require it by default).

### `HTTP 403`

- Your WordPress user account may not have permission to create posts. Check the user role (needs at minimum **Author**).
- Some security plugins (Wordfence, iThemes Security) block REST API access. Whitelist JARVIS's IP or disable REST API protection rules.

### `HTTP 503 / Connection Error`

- Cloudflare or another WAF may be blocking requests. JARVIS includes a browser-like `User-Agent` header to reduce blocking.
- Enable the **REST API passthrough** rule in Cloudflare if using their firewall.

### Posts publishing but CSS not showing

- Some WordPress themes strip `<style>` tags from post content for security.
- Use a plugin such as **Simple Custom CSS and JS** to add the JARVIS CSS globally to your theme instead.
- Or set `WP_POST_STATUS=draft` and add the CSS to your theme's `style.css` manually.

---

## Disabling WordPress Publishing

Leave `WP_URL`, `WP_USER`, and `WP_APP_PASSWORD` empty in `.env`. JARVIS will log a skip message and continue with the rest of the daily report pipeline (Telegram, audio).
