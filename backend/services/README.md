# Backend Services Module

## Purpose
Core background services including item worker processing, audio podcast generation, MCP server client handshakes, subscriber preferences, intelligence query assistant, and telemetry tracking.

## Contained Modules
- `worker_processor.py`: Item scraping and AI analysis pipeline worker.
- `audio_generator.py`: Edge-TTS audio generator for podcast briefs.
- `mcp_client.py`: Model Context Protocol transport client.
- `runtime_state.py`: Global pipeline phase banner and queue state telemetry.
- `subscriber_store.py`: Subscriber storage.
- `telemetry.py`: Performance telemetry recorder.
- `intelligence.py`: Q&A intelligence helper.

## Dependencies
- `edge_tts`, `requests`, `backend.ai.ai_router`, `backend.database.jarvis_db`.

## Entry Points
- `run_worker(items)`: Processes a batch of queued articles.
- `generate_audio_summary(text, output_path)`: Generates MP3 audio brief.
- `test_mcp_server(config)`: Tests MCP transport connection.

## Important Files
- [`worker_processor.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/services/worker_processor.py)
- [`audio_generator.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/services/audio_generator.py)
- [`mcp_client.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/services/mcp_client.py)
