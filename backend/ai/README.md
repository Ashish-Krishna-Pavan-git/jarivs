# Backend AI Module

## Purpose
Multi-tier LLM routing, rate slot lock management, dynamic provider failover, and prompt formatting for intelligence analysis.

## Contained Modules
- `ai_router.py`: LLM routing logic, rate slot locks, call latency tracking, and provider fallbacks.

## Dependencies
- `google-genai`, `groq`, `requests`, `backend.database.jarvis_db`.

## Entry Points
- `ai_analyze_article(article_data)`: Single-article threat analysis.
- `ai_digest(articles)`: Synthesis digest generation.
- `get_ai_status()`: Active model status telemetry.

## Important Files
- [`ai_router.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/ai/ai_router.py)
