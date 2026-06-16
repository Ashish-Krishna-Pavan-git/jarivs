# JARVIS — Intelligence System Setup Guide

## What It Does
Every 8 hours:
1. Fetches articles from 30+ sources (cybersec, AI, tech, phones, hardware)
2. Scrapes full article content
3. AI analyzes each article (severity, summary, CVEs, actors)
4. 🚨 CRITICAL/HIGH → instant Telegram alert
5. 📊 After full cycle → structured digest to Telegram (Medium/Low items)
6. 🗓 Every morning at 7 AM UTC → Daily summary correlating all 3 cycles

---

## Severity Routing
| Level | Action |
|-------|--------|
| CRITICAL | Instant Telegram alert |
| HIGH | Instant Telegram alert |
| MEDIUM | 8hr digest |
| LOW | 8hr digest |
| MINIMAL | Saved only, not sent |

---

## Recommended Model: Phi-4-mini

**Why Phi-4-mini over other 3B models?**
- Best instruction-following in class
- Structured JSON output — critical for this pipeline
- Great analytical reasoning for summaries
- 3.8B parameters, fits in Q4 with ~2.3GB RAM
- Microsoft-trained on high quality data

**Alternatives if Phi-4-mini is too slow on your phone:**
- `qwen2.5:3b` — Fast, good at structured output, 2nd best choice
- `llama3.2:3b` — Solid fallback, slightly weaker at JSON
- `gemma3:2b` — Smallest, use only if 3b models lag

---

## WINDOWS SETUP (Ollama)

### 1. Install Ollama
Download from: https://ollama.com/download/windows
Run installer, then open PowerShell:
```
ollama --version
```

### 2. Pull Phi-4-mini
```
ollama pull phi4-mini
```
> This downloads ~2.3GB

### 3. Start Ollama server
```
ollama serve
```
> Runs on http://localhost:11434 by default

### 4. Install Python dependencies
```
pip install -r requirements.txt
```

### 5. Configure .env
Copy `.env.example` to `.env` and fill in:
```
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
OLLAMA_MODEL=phi4-mini
```

### 6. Run
```
python scheduler.py
```

---

## TERMUX SETUP (llama.cpp)

### 1. Install dependencies
```bash
pkg update && pkg upgrade
pkg install python git cmake wget
pip install -r requirements.txt
```

### 2. Install llama.cpp (prebuilt binary)
```bash
# Download prebuilt ARM64 binary
wget https://github.com/ggerganov/llama.cpp/releases/latest/download/llama-b3619-bin-android-arm64-v8a.zip

unzip llama-b3619-bin-android-arm64-v8a.zip -d llamacpp
chmod +x llamacpp/llama-server
```

> Or use latest release from: https://github.com/ggerganov/llama.cpp/releases

### 3. Download Phi-4-mini Q4 model
```bash
mkdir -p ~/models
cd ~/models

# Download from HuggingFace
wget "https://huggingface.co/microsoft/Phi-4-mini-instruct-GGUF/resolve/main/Phi-4-mini-instruct-Q4_K_M.gguf"
```
> ~2.3GB download — do on WiFi

**Alternative (smaller/faster):**
```bash
wget "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
```

### 4. Start llama.cpp server
```bash
# Start server (run this first, keep it running)
~/llamacpp/llama-server \
  -m ~/models/Phi-4-mini-instruct-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 8192 \
  --threads 4 \
  -ngl 0
```

> `-ngl 0` = CPU only (no GPU on Snapdragon in Termux without special builds)
> `--threads 4` = use 4 CPU threads; try 6 if stable

### 5. Keep it running with tmux
```bash
# Install tmux
pkg install tmux

# Start a tmux session
tmux new -s jarvis

# Inside tmux — start llama.cpp server
~/llamacpp/llama-server -m ~/models/Phi-4-mini-instruct-Q4_K_M.gguf --port 8080 --threads 4

# Split window (Ctrl+B then %)
# In second pane — start scheduler
cd ~/jarvis
python scheduler.py

# Detach from tmux: Ctrl+B then D
# Reattach later: tmux attach -t jarvis
```

### 6. Prevent Termux from sleeping
```bash
# Keep CPU awake while running
termux-wake-lock

# Install Termux:API app from F-Droid if termux-wake-lock not found
```

### 7. Configure .env
```
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
LLAMACPP_URL=http://localhost:8080
```

---

## How to Get Telegram Bot Token + Chat ID

1. Open Telegram → search `@BotFather`
2. Send `/newbot` → follow steps → copy the token
3. Add your bot to a channel/group, OR just message it directly
4. Get your Chat ID: visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   Send any message to bot first, then check the JSON for `chat.id`

---

## Model Performance on Snapdragon 778G

| Model | RAM (Q4) | Speed (tokens/s) | Quality |
|-------|----------|------------------|---------|
| Phi-4-mini (3.8B) | ~2.3GB | ~8-12 tok/s | ⭐⭐⭐⭐⭐ |
| Qwen2.5:3B | ~2.0GB | ~12-15 tok/s | ⭐⭐⭐⭐ |
| Llama3.2:3B | ~2.0GB | ~12-15 tok/s | ⭐⭐⭐ |
| Gemma3:2B | ~1.4GB | ~18-22 tok/s | ⭐⭐⭐ |

> For 600 articles × 40 tokens/s avg = ~4-5 hours processing time. This is expected and fine.

---

## File Structure
```
jarvis/
├── scheduler.py          ← Run this to start everything
├── config.py             ← Central settings
├── collector.py          ← RSS fetcher (30+ sources)
├── scraper.py            ← Full article scraper
├── dedupe.py             ← Deduplication (bug fixed)
├── queue_manager.py      ← Job queue
├── ai_router.py          ← Local AI (Ollama/llama.cpp)
├── worker_processor.py   ← Core processing pipeline
├── notifier.py           ← Telegram alerts & digests
├── intelligence.py       ← Pattern analysis
├── storage.py            ← Save JSON + Markdown
├── dailySummary.py       ← Morning daily report
├── archive_manager.py    ← Auto-archive old data
├── telemetry.py          ← Stats tracking
├── internet_monitor.py   ← Connection check
├── .env                  ← Your config (never commit this)
├── .env.example          ← Template
├── requirements.txt
└── data/
    ├── processed/        ← Articles by date
    ├── daily/            ← Cycle digests + daily reports
    └── archive/          ← Compressed old data (zips)
```

---

## Quick Test Commands

```bash
# Test Telegram
python teletest.py

# Test one cycle (Windows with Ollama running)
python scheduler.py

# Test daily summary only
python dailySummary.py

# Check what's in queue
python -c "from queue_manager import stats; print(stats())"

# Check telemetry
python -c "from telemetry import print_stats; print_stats()"
```

---

## Troubleshooting

**llama.cpp server crashes on article processing:**
Reduce context size: `--ctx-size 4096`

**5B model lags/crashes:**
Stay with 3B (Phi-4-mini Q4 or Qwen2.5:3B). 5B needs ~3.5GB which exhausts your available RAM.

**7B resets phone:**
7B Q4 needs ~4.5GB — impossible on 6GB with Android overhead. Do not attempt.

**Articles not being summarized:**
Check llama.cpp server is running: `curl http://localhost:8080/health`

**Telegram not sending:**
Run `python teletest.py` to verify token and chat ID.