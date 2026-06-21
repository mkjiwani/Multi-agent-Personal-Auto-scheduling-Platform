# NEXUS — Multi-Agent Personal Auto-Scheduling Platform

A locally-hosted multi-agent intelligence platform powered by **Qwen3** (via Ollama) that automates daily information gathering, email management, stock tracking, news summarization, and document Q&A — all through a live web dashboard with scheduled HTML email digests.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Web Dashboard (localhost:8000)                │
│  Overview | AI-Times | Mailman | Wallstreet | News | DocVault    │
└──────────────────────────┬───────────────────────────────────────┘
                           │ WebSocket + REST API
┌──────────────────────────┴───────────────────────────────────────┐
│                    FastAPI Server (main.py)                       │
│  Static files · REST routes · WebSocket · APScheduler digests    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────────┐
│                       ORCHESTRATOR                                │
│  • Resource Monitor (CPU/RAM/Disk every 5s)                      │
│  • Alarm System (configurable thresholds)                        │
│  • LLM Semaphore (1 agent at a time, 300s timeout)               │
│  • Agent Supervisor (subprocess management, auto-restart ×3)     │
│  • Digest Scheduler (APScheduler cron jobs)                      │
└──┬──────────┬──────────┬──────────┬──────────┬───────────────────┘
   │          │          │          │          │
┌──┴──┐  ┌───┴──┐  ┌───┴───┐  ┌──┴───┐  ┌──┴────┐
│AI-  │  │Mail- │  │Wall-  │  │News  │  │Doc-   │
│Times│  │man   │  │street │  │Brief │  │Vault  │
└──┬──┘  └──┬───┘  └──┬────┘  └──┬───┘  └──┬────┘
   │        │         │          │          │
   ▼        ▼         ▼          ▼          ▼
YouTube   Gmail    Yahoo Fin.  NewsAPI   Local Docs
Data API  OAuth2   yfinance    .org     (PDF/DOCX/TXT)
   │        │         │          │
   └────────┴────┬────┴──────────┘
                 │
         ┌───────┴───────┐
         │  Ollama/Qwen3 │  (Local LLM — localhost:11434)
         └───────┬───────┘
                 │
         ┌───────┴───────┐
         │    SQLite      │  (data/platform.db — cache + persistence)
         └───────────────┘
```

---

## Prerequisites

Before starting, ensure you have the following installed on your machine:

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| **Python** | 3.12+ | `python3 --version` |
| **pip** | Latest | `pip --version` |
| **Ollama** | Latest | `ollama --version` |
| **Git** | Any | `git --version` |
| **Web browser** | Any modern browser | — |

---

## Step-by-Step Setup (New Machine)

### Step 1: Install Python 3.12+

**macOS:**
```bash
brew install python@3.12
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install python3.12 python3.12-venv python3-pip
```

**Windows:**
Download from [python.org/downloads](https://www.python.org/downloads/) — check "Add to PATH" during installation.

### Step 2: Install Ollama

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download installer from [ollama.com/download](https://ollama.com/download).

### Step 3: Start Ollama and Pull the Model

```bash
# Start the Ollama server (leave this terminal open)
ollama serve

# In a NEW terminal, pull the Qwen3 model (~5 GB download)
ollama pull qwen3

# Verify it's running
curl http://localhost:11434/api/tags
```

### Step 4: Clone / Copy the Project

```bash
# If using Git:
git clone <your-repo-url>
cd Assingment2

# Or copy the project folder to your machine
```

### Step 5: Run Automated Setup

```bash
make setup
```

This runs `setup.sh` which:
- Creates a Python virtual environment (`venv/`)
- Installs all dependencies from `requirements.txt`
- Creates `data/`, `tokens/`, `credentials/` directories
- Copies `.env.example` → `.env` if `.env` doesn't exist
- Attempts to pull the Qwen3 model

**If `make` is not available**, run manually:
```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate          # Windows
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p data tokens credentials
cp .env.example .env
```

### Step 6: Get API Keys

You need **three API keys** from external services:

#### 6a. YouTube Data API v3 (for AI-Times agent)
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Navigate to **APIs & Services → Library**
4. Search for **"YouTube Data API v3"** → Enable it
5. Go to **APIs & Services → Credentials → Create Credentials → API Key**
6. Copy the API key

#### 6b. Gmail OAuth 2.0 (for Mailman agent)
1. In the same Google Cloud project, enable the **Gmail API**
2. Go to **APIs & Services → OAuth consent screen**
   - Choose **External** user type
   - Fill in app name and email
   - Add scope: `https://www.googleapis.com/auth/gmail.modify`
   - Add your Gmail address as a **Test User**
   - **Important:** Click **"Publish App"** to move from Testing → Production (otherwise tokens expire every 7 days)
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Download the JSON file
4. Save it as: `credentials/gmail_credentials.json`

#### 6c. NewsAPI (for News Briefer agent)
1. Go to [newsapi.org](https://newsapi.org) → Register for free
2. Copy your API key (free tier: 100 requests/day)

#### 6d. Gmail App Password (for sending digest emails via SMTP)
1. Go to [Google Account → Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already enabled
3. Go to **App Passwords** → Generate one for "Mail"
4. Copy the 16-character password

### Step 7: Configure Environment Variables

Edit the `.env` file with your API keys:

```bash
# Open in your editor
nano .env    # or: code .env
```

Fill in these required values:

```bash
# YouTube (AI-Times)
YOUTUBE_API_KEY=AIza...your_key_here

# NewsAPI (News Briefer)
NEWSAPI_KEY=your_newsapi_key_here

# Gmail key people to star/alert (comma-separated)
GMAIL_KEY_PEOPLE=boss@company.com,manager@company.com

# SMTP for sending digest emails
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=your_email@gmail.com

# Stock watchlist (customize as needed)
STOCK_WATCHLIST=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA

# Digest schedule (24h format)
SCHEDULE_AI_TIMES=08:00
SCHEDULE_MAILMAN=09:00
SCHEDULE_WALLSTREET=07:30
SCHEDULE_NEWS=08:30
```

### Step 8: Authenticate Gmail

```bash
make auth-gmail
```

This opens your browser for Google OAuth consent. Sign in, grant access, and the token is saved to `tokens/gmail_token.json`. You only need to do this **once per machine** (tokens auto-refresh).

### Step 9: Start the Platform

```bash
make run
```

Open **http://localhost:8000** in your browser.

For lower memory usage (no file watcher):
```bash
make run-prod
```

---

## Agents

### Agent 1: AI-Times (YouTube AI Videos)
- Fetches latest AI/ML YouTube videos via YouTube Data API v3
- Categorizes into **AI News** and **AI Personalities**
- Sends daily HTML email digest at configured time
- Dashboard: video thumbnails with links, manual refresh

### Agent 2: Mailman (Gmail Automation)
- Scans Gmail inbox via OAuth 2.0
- Classifies emails into 7 priority-ordered categories using LLM:
  **Urgent → Action Required → Follow-Up → Newsletter → Notification → Personal → Other**
- Applies Gmail labels (`AutoClass/Category`) automatically
- Stars emails from configurable key-people list
- Skips already-classified emails (persistent via SQLite)
- Auto-refreshes expired OAuth tokens
- Dashboard: category breakdown, email list with AI summaries, manual scan

### Agent 3: Wallstreet Wolf (Stock Tracker)
- Tracks configurable stock watchlist via Yahoo Finance
- Identifies top 5 gainers and losers
- Fetches currency pairs (EUR/USD, GBP/USD, etc.) and metals (Gold, Silver)
- Generates witty LLM market commentary
- Sends daily market brief email
- Dashboard: stock grid, gainers/losers, currencies, metals, commentary

### Agent 4: News Briefer (News Summarization)
- Fetches articles from NewsAPI across configurable categories
- Generates 2-3 sentence AI summaries per article
- Creates a cohesive "Daily Brief" narrative
- Sends daily news digest email
- Dashboard: article cards with summaries, category filters, daily brief

### Agent 5: DocVault (Local Document RAG)
- Indexes local PDF, DOCX, and TXT files using TF-IDF
- Incremental reindexing (only changed/new files)
- Ask questions about your documents — retrieves relevant chunks + LLM answer
- Persistent index cache (survives restarts)
- Dashboard: folder management, search interface, query history

#### DocVault Use-Case Proposal

DocVault addresses a critical pain point for knowledge workers who accumulate large volumes of local documents — meeting notes, technical specs, contracts, research papers, internal wikis exported as PDF — but struggle to retrieve specific information without manually re-reading files. Consider a network engineer maintaining hundreds of runbook PDFs and vendor datasheets: when a production incident occurs at 2 AM, they need to instantly locate the exact troubleshooting procedure buried across dozens of documents. DocVault solves this by building a TF-IDF vector index over all ingested files, chunking content into semantically meaningful passages, and using cosine similarity to retrieve the most relevant fragments for any natural-language query. The retrieved context is then passed to the local Qwen3 LLM, which synthesizes a coherent answer grounded in the source material — effectively creating a private, offline ChatGPT that only knows your documents. Unlike cloud-based RAG solutions, DocVault keeps all data on-device (no API calls, no data leaving your machine), making it suitable for sensitive corporate documents, legal contracts, or personal journals. The incremental indexing ensures that newly added or modified files are processed in seconds rather than requiring a full re-index, and the persistent cache means the system is query-ready immediately after restart without re-processing the entire corpus.

---

## Dashboard Features

- **Real-time system metrics** — CPU, RAM, Disk gauges with animated SVG rings
- **Agent status cards** — running/stopped/crashed with restart buttons
- **LLM semaphore status** — shows which agent holds the LLM and who's waiting
- **Configurable digest schedule** — time pickers for each agent's email digest
- **WebSocket live updates** — metrics pushed every 5 seconds without polling
- **Alarm banner** — alerts when CPU/RAM/Disk exceed thresholds

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make setup` | Full setup — venv, dependencies, model pull |
| `make run` | Start platform (with hot-reload on `src/` and `frontend/`) |
| `make run-prod` | Start without file watcher (lower memory) |
| `make auth-gmail` | Run Gmail OAuth flow |
| `make pull-model` | Pull/update Qwen3 model |
| `make check-ollama` | Verify Ollama is running |
| `make test` | Run test suite |
| `make clean` | Remove `__pycache__` and temp files |

---

## Project Structure

```
├── Makefile                 # Build/run commands
├── requirements.txt         # Python dependencies
├── setup.sh                 # Automated setup script
├── .env.example             # Environment template
├── .env                     # Your API keys (git-ignored)
├── README.md
│
├── src/
│   ├── main.py              # FastAPI entry point + startup/shutdown
│   ├── config.py            # All settings (pydantic-settings, reads .env)
│   ├── database.py          # SQLAlchemy models + async session
│   ├── auth_gmail.py        # Gmail OAuth token generation
│   │
│   ├── orchestrator/
│   │   ├── orchestrator.py  # Central lifecycle + digest scheduling
│   │   ├── agent_supervisor.py  # Subprocess management + auto-restart
│   │   ├── monitor.py       # CPU/RAM/Disk resource monitor
│   │   └── alarm.py         # Threshold alarm system
│   │
│   ├── agents/
│   │   ├── base_agent.py    # Abstract base class (run loop, heartbeat)
│   │   ├── ai_times.py      # YouTube AI video agent
│   │   ├── mailman.py       # Gmail classification agent
│   │   ├── wallstreet_wolf.py  # Stock tracking agent
│   │   ├── news_briefer.py  # News summarization agent
│   │   └── docvault.py      # Local document RAG agent
│   │
│   ├── llm/
│   │   └── ollama_client.py # Async Ollama client (semaphore, think-mode)
│   │
│   ├── email_service/
│   │   └── sender.py        # SMTP HTML email sender
│   │
│   └── api/
│       ├── routes_orchestrator.py  # System health, metrics, schedules
│       ├── routes_ai_times.py      # Video endpoints
│       ├── routes_mailman.py       # Email endpoints
│       ├── routes_wallstreet.py    # Stock endpoints
│       ├── routes_custom.py        # News endpoints
│       └── routes_docvault.py      # DocVault Q&A endpoints
│
├── frontend/
│   ├── index.html           # Dashboard SPA
│   ├── css/style.css        # Glassmorphism dark theme
│   └── js/
│       ├── app.js           # WebSocket + tab routing
│       ├── orchestrator.js  # Metrics, gauges, agent cards, schedules
│       ├── ai_times.js      # Video grid rendering
│       ├── mailman.js       # Email list + categories
│       ├── wallstreet.js    # Stock grid + commentary
│       ├── custom.js        # News articles + daily brief
│       └── docvault.js      # Document search UI
│
├── data/
│   ├── platform.db          # SQLite database (auto-created)
│   └── docvault_cache/      # TF-IDF index + chunks (auto-created)
│
├── credentials/
│   └── gmail_credentials.json  # OAuth client secret (you provide)
│
└── tokens/
    └── gmail_token.json     # OAuth access/refresh token (auto-generated)
```

---

## Persistent Storage (SQLite)

All agent data is persisted to `data/platform.db`:

| Table | Agent | Contents |
|-------|-------|----------|
| `cached_videos` | AI-Times | Video ID, title, channel, thumbnail, category |
| `email_records` | Mailman | Message ID, sender, subject, classification, AI summary |
| `stock_snapshots` | Wallstreet Wolf | Ticker, price, change %, volume (historical) |
| `news_articles` | News Briefer | Title, source, description, category, AI summary |
| `system_metrics` | Monitor | CPU, RAM, Disk snapshots |
| `agent_logs` | Supervisor | Agent activity logs |

Data survives restarts — agents load from DB on startup and write after each cycle.

---

## Troubleshooting

### "Ollama connection refused"
```bash
# Start the Ollama server
ollama serve
# Verify
make check-ollama
```

### "Gmail token expired or revoked"
```bash
# Re-authenticate (opens browser)
make auth-gmail
```
To prevent 7-day token expiry: publish your OAuth app from Testing → Production in Google Cloud Console.

### "No module named 'src.agents.docvault'"
Ensure the file `src/agents/docvault.py` exists. If copying between machines, verify all files transferred.

### High memory usage (90%+)
```bash
# Use production mode (no file watcher)
make run-prod
```
The `--reload` flag with Uvicorn can consume excessive memory on deep directory trees (like OneDrive/cloud-synced folders).

### "YouTube API 429 Too Many Requests"
The YouTube Data API has a daily quota (10,000 units). Each search costs 100 units. Reduce `max_results` or increase the fetch interval.

### DocVault indexing is slow
DocVault indexes files incrementally — only new/changed files are processed. The first index of a large folder may take time. Subsequent runs are fast.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | No | `qwen3` | LLM model name |
| `YOUTUBE_API_KEY` | Yes | — | YouTube Data API v3 key |
| `GMAIL_TOKEN_FILE` | No | `tokens/gmail_token.json` | OAuth token path |
| `GMAIL_CREDENTIALS_FILE` | No | `credentials/gmail_credentials.json` | OAuth client secret path |
| `GMAIL_KEY_PEOPLE` | No | — | Comma-separated emails to star |
| `NEWSAPI_KEY` | Yes | — | NewsAPI.org API key |
| `NEWS_CATEGORIES` | No | `technology,business,science` | News categories to fetch |
| `STOCK_WATCHLIST` | No | `AAPL,MSFT,...` | Comma-separated tickers |
| `SMTP_HOST` | No | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | No | `587` | SMTP port |
| `SMTP_USERNAME` | Yes* | — | SMTP login email |
| `SMTP_PASSWORD` | Yes* | — | Gmail App Password |
| `EMAIL_FROM` | Yes* | — | Digest sender address |
| `EMAIL_TO` | Yes* | — | Digest recipient address |
| `SCHEDULE_AI_TIMES` | No | `08:00` | AI-Times digest time (24h) |
| `SCHEDULE_MAILMAN` | No | `09:00` | Mailman summary time (24h) |
| `SCHEDULE_WALLSTREET` | No | `07:30` | Market brief time (24h) |
| `SCHEDULE_NEWS` | No | `08:30` | News digest time (24h) |
| `ALARM_CPU_THRESHOLD` | No | `90` | CPU alarm % |
| `ALARM_RAM_THRESHOLD` | No | `90` | RAM alarm % |
| `ALARM_DISK_THRESHOLD` | No | `90` | Disk alarm % |

*Required only if you want digest emails to be sent.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| LLM | Ollama + Qwen3 (local, no cloud API) |
| Database | SQLite via SQLAlchemy + aiosqlite |
| Frontend | HTML/CSS/JS (no framework) |
| Email | SMTP via aiosmtplib |
| Scheduling | APScheduler (cron triggers) |
| Search/RAG | scikit-learn TF-IDF + joblib |
| Real-time | WebSocket (metrics push every 5s) |
    ├── routes_orchestrator.py
    ├── routes_ai_times.py
    ├── routes_mailman.py
    ├── routes_wallstreet.py
    ├── routes_custom.py
    └── websocket.py
frontend/                # Web dashboard (HTML/JS/CSS)
```

## Agent-4: News Briefer (Use-Case Proposal)

The News Briefer agent solves the problem of information overload by automatically curating and summarizing news from multiple categories (technology, business, science, health). It fetches top headlines via NewsAPI.org, uses the local Qwen3 LLM to generate concise summaries of each article, and produces a cohesive "Daily Brief" narrative that captures the day's most important stories. Users can configure which categories and countries to track, and receive a formatted HTML email digest on a configurable schedule. The dashboard tab provides categorized article cards with AI summaries and manual refresh capability.

## Agent-5: DocVault — Local RAG

DocVault indexes local documents (PDF, DOCX, TXT, MD) and answers questions using Retrieval-Augmented Generation (TF-IDF + LLM).

### Features
- **Multi-folder support** — add multiple document folders via UI or API
- **Incremental reindex** — only re-reads changed/new files (uses mtime + size)
- **Persistent index** — TF-IDF index cached to `data/docvault_cache/` (survives restarts)
- **Progress indicators** — logs show file-by-file progress during indexing
- **Corruption-tolerant** — gracefully handles corrupted DOCX files (CRC bypass fallback)

### Usage

1. Place documents in the `documents/` folder, or add folders via the API:
   ```bash
   curl -X POST http://localhost:8000/api/docvault/folders/add \
     -H "Content-Type: application/json" \
     -d '{"folder_path": "/path/to/your/docs"}'
   ```
2. Indexing happens automatically (includes reindex on folder add)
3. Ask questions:
   ```bash
   curl -X POST http://localhost:8000/api/docvault/query \
     -H "Content-Type: application/json" \
     -d '{"question": "What are the new features in release 7.3.5?"}'
   ```
4. Check status: `GET /api/docvault/status`
5. Force reindex: `POST /api/docvault/reindex`

## Troubleshooting

**"Address already in use" on port 8000:**
```bash
lsof -ti :8000 | xargs kill -9
make run
```

**"No module named X" (e.g. joblib, sklearn):**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Ollama not responding / connection refused:**
```bash
make check-ollama
# If not running:
ollama serve
# In another terminal, verify:
curl http://localhost:11434/api/tags
```

**LLM generation errors (empty responses):**  
Usually caused by high CPU/RAM. The local Qwen3 model needs ~8 GB RAM. Close other heavy applications or reduce agents running simultaneously.

**OOM killed (exit code 137):**  
The system runs 5 agents + Ollama concurrently. Recommend **16+ GB RAM**. If constrained, disable non-essential agents in the orchestrator config.

**Gmail OAuth errors:**  
Re-run `make auth-gmail` to refresh the token. Ensure `credentials/gmail_credentials.json` exists and your Google Cloud project has Gmail API enabled with your email as a test user.

**DocVault DOCX warnings:**  
Some DOCX files (especially from OneDrive/SharePoint) have corrupted zip structures. DocVault handles these gracefully — a warning is logged but indexing continues. The text is extracted via an XML fallback when possible.
