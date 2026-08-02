# AI Multi-Tier Routing System

JARVIS utilizes a multi-tier AI routing framework ([`ai_router.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/ai_router.py)) to process articles, synthesize digests, and answer user queries efficiently.

## Task Tiers & Routing Paths

1. **PREMIUM Tier (Daily/Weekly Summaries)**:
   - Primary: `gemini-2.5-pro`
   - Secondary Fallback: `gemini-2.5-flash`
   - Tertiary Fallback: `groq` (`llama-3.3-70b-versatile`)

2. **DIGEST Tier (Cycle Digests)**:
   - Primary: `gemini-2.5-flash`
   - Fallback: `groq` (`llama-3.3-70b-versatile`)

3. **ARTICLE Tier (Per-Article Processing)**:
   - Primary: `groq` (`llama-3.1-8b-instant`)
   - Fallback: `gemini-2.5-flash`

4. **TEXT Tier (Q&A / Plain Prose)**:
   - Primary: `gemini-2.5-flash`
   - Fallback: `groq` (`llama-3.3-70b-versatile`)

---

## Rate Slot Locks & Failure Backoff

- **Rate Limits**:
  - Gemini Pro calls enforce a 13-second minimum slot interval (`_GEMINI_PRO_INTERVAL = 13.0`).
  - Groq calls enforce rate slot locks per model.
- **Automatic Block & Fallback**:
  - If a provider returns HTTP 429, rate-limit, or quota errors, `block_model_provider(pname, 180, reason)` dynamically blocks the provider for 3 minutes.
  - The router automatically tries the next provider in the route sequence without interrupting the pipeline.

---

## AI Call Tracking & Telemetry

Every call is logged in memory for live visibility via `get_ai_status()`:
- `last_task`: Task tier executed (`article`, `digest`, `premium`, `text`).
- `last_provider`: Provider name used.
- `last_model`: Exact model name.
- `last_latency_ms`: Call duration in milliseconds.
- `last_fallback_used`: Boolean indicating whether a fallback provider was used.
- `total_calls`, `total_fallbacks`, `total_failures`: System-wide lifetime counters.
