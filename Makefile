VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help install lint format test coverage demo review ui clean

help:
	@echo "Available commands:"
	@echo "  make install   Install dependencies into virtual environment"
	@echo "  make lint      Run code quality and type checks"
	@echo "  make format    Auto-format code"
	@echo "  make test      Run unit and integration tests"
	@echo "  make coverage  Run tests with coverage reporting"
	@echo "  make demo      Run automated demo across all sample diffs"
	@echo "  make review    Run review on a sample diff"
	@echo "  make ui        Launch web UI"
	@echo "  make clean     Remove temporary files and caches"

install:
	$(PIP) install -r requirements.txt

lint:
	$(PYTHON) -m ruff check core agents plugins cli reporting tests config
	$(PYTHON) -m black --check core agents plugins cli reporting tests config
	$(PYTHON) -m mypy core agents plugins reporting cli

format:
	$(PYTHON) -m ruff check --fix core agents plugins cli reporting tests config
	$(PYTHON) -m black core agents plugins cli reporting tests config

test:
	$(PYTHON) -m pytest -v tests/

coverage:
	$(PYTHON) -m pytest --cov=core --cov=agents --cov-report=term-missing --cov-report=html tests/

demo:
	$(PYTHON) -m cli.main demo

review:
	$(PYTHON) -m cli.main review --diff samples/diffs/05_mixed_realistic.diff

ui:
	$(PYTHON) -m streamlit run ui/app.py

clean:
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
