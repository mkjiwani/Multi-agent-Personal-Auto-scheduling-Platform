.PHONY: setup run test pull-model clean lint

# Setup the project (create venv, install deps, pull model)
setup:
	chmod +x setup.sh && ./setup.sh

# Run the platform
run:
	. venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir src --reload-dir frontend

# Run without reload (production-like, lower memory)
run-prod:
	. venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1

# Run tests
test:
	. venv/bin/activate && pytest tests/ -v

# Pull the Qwen3 model
pull-model:
	ollama pull qwen3

# Gmail OAuth setup
auth-gmail:
	. venv/bin/activate && python -m src.auth_gmail

# Clean generated files
clean:
	rm -rf __pycache__ .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Check Ollama is running
check-ollama:
	@curl -s http://localhost:11434/api/tags > /dev/null && echo "✓ Ollama is running" || echo "✗ Ollama is not running — start it with: ollama serve"
