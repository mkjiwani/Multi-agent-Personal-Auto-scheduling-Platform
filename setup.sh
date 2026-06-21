#!/bin/bash
# =============================================================================
# Multi-Agent Platform - One-Command Setup (macOS/Linux)
# =============================================================================
set -e

echo "=== Multi-Agent Auto-Scheduling Platform Setup ==="
echo ""

# Check Python 3.12+
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.12+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION found"

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "WARNING: Ollama not found. Install from https://ollama.ai"
    echo "  After installing, run: ollama pull qwen3"
else
    echo "✓ Ollama found"
    echo "  Pulling Qwen3 model (this may take a while)..."
    ollama pull qwen3 || echo "  WARNING: Could not pull qwen3. Ensure Ollama is running."
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
echo "✓ Virtual environment ready"

# Activate and install dependencies
echo ""
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# Create data directory
mkdir -p data tokens credentials

# Copy .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠ Created .env from .env.example — edit it with your API keys!"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys (YouTube, Gmail, NewsAPI, SMTP)"
echo "  2. Set up Gmail OAuth: python src/auth_gmail.py"
echo "  3. Start the platform: make run"
echo ""
