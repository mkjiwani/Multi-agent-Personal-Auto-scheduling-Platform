# NEXUS Platform — Documentation

## Overview
NEXUS is a multi-agent auto-scheduling platform that runs locally. It uses Qwen3 as the LLM backbone via Ollama and orchestrates 5 AI agents to handle different aspects of your digital life.

## Agents

### 1. AI-Times
Fetches trending AI videos from YouTube, ranks them by view count, and generates short summaries using the LLM.

### 2. Mailman
Connects to Gmail via OAuth, fetches recent emails, and classifies them into categories: Urgent, Action Required, Follow-Up, Newsletter, Notification, Personal, Other.

### 3. Wallstreet Wolf
Tracks a customizable stock watchlist using Yahoo Finance. Shows top gainers/losers, currency rates, and generates LLM market commentary.

### 4. News Briefer
Fetches top news from NewsAPI across configurable categories (technology, business, science). Generates per-article summaries and a cohesive daily brief.

### 5. DocVault (RAG)
A local Retrieval-Augmented Generation agent. Indexes documents from a configurable folder, chunks them, builds a TF-IDF index, and answers questions by retrieving relevant passages and generating answers with the LLM.

## Architecture
- Backend: FastAPI + Uvicorn
- Frontend: Vanilla HTML/CSS/JS (no framework)
- LLM: Qwen3 8B via Ollama (local)
- Orchestrator: Agent supervisor with health monitoring, auto-restart, and resource alarms
- Database: SQLite (for future persistence)

## Configuration
All settings are in the `.env` file. Key variables:
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL` — LLM configuration
- `RAG_FOLDER_PATH` — Folder for DocVault to index
- `STOCK_WATCHLIST` — Comma-separated tickers
- `NEWS_CATEGORIES` — News topics to track
