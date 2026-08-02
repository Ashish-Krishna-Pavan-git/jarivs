# Administrative Command Center & Diagnostics

The Command Center & Testing page (`/admin/#testing`) is an interactive administrative interface for operational management, component health testing, pipeline control, and maintenance cleanup.

## Features & Operation Controls

### 1. Pipeline Pause / Resume Toggle
- **Endpoint**: `POST /api/admin/testing/pipeline-toggle`
- **Behavior**: Toggles `pipeline:paused` in SQLite database `app_settings`.
- **Purpose**: Temporarily holds scheduled collection and daily cycles during system maintenance without stopping the application container.

### 2. Manual Cycle & Execution Runners
- **Run Collection Cycle**: Invokes `collect_all()` and `get_new_articles()` to ingest fresh articles from enabled feeds into the processing queue.
- **Run AI Analysis Cycle**: Tests multi-tier LLM analysis, CVE extraction, and severity classification on sample or queued content.
- **Test All Notification Channels**: Triggers an alert test across all active Telegram chats and Slack webhooks, displaying inline delivery success or HTTP failure details.
- **Run Report Generation**: Synthesizes current queue items into an executive intelligence digest.

### 3. Component Health & Reachability Diagnostics
- **Test Every Provider** (`POST /api/admin/testing/test-providers`): Verifies API keys, rate slot availability, and response latency for Gemini, Groq, Ollama, and OpenAI-compatible providers.
- **Test Every Collector** (`POST /api/admin/testing/test-collectors`): Performs HTTP reachability and RSS entry count checks for all enabled source feeds.
- **Test Every MCP Server** (`POST /api/admin/testing/test-mcp`): Executes protocol handshakes for HTTP and STDIO MCP servers.

---

## One-Click Maintenance Cleanup (`clear_all_test_data`)

The Command Center features a dedicated **"Clear All Test Data"** maintenance action designed for test data cleanup without disrupting core app configuration.

### What is Cleared:
- Daily and archive digest reports (`/data/daily`, `/data/archive`)
- Event logs and alert history (`event_logs` table in `jarvis.db`)
- In-memory queue entries and worker queue state
- Scraped raw articles and processed article JSON files (`/data/processed`, `/data/raw_articles`)
- Deduplication fingerprint cache (`seen.json` and in-memory cache)
- Audio podcast MP3 files (`/data/audio`)

### What is Preserved:
- Database schema structure & migration history
- User accounts and active session credentials
- Curated source feed configurations
- Model provider settings & route priority tables
- Encrypted notification channel targets
- App settings & environment parameters

### Post-Cleanup Verification Report
Upon completion, the endpoint executes an automatic verification check and returns detailed counts. The UI displays a verification banner confirming that counts for reports, articles, queue entries, and fingerprints are zero (`✓ Verification Passed: Test Data Fully Cleared`).
