.PHONY: help install dev lint format test test-unit test-integration build clean check publish

PYTHON ?= .venv/bin/python
UV     ?= uv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install package in editable mode
	$(UV) sync
	$(PYTHON) -m pip install -e .

dev: ## Install dev dependencies
	$(UV) sync --group dev

lint: ## Run ruff linter
	$(PYTHON) -m ruff check src/ tests/

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format src/ tests/
	$(PYTHON) -m ruff check --fix src/ tests/

test: ## Run all tests (requires OmniFocus running)
	$(PYTHON) -m pytest tests/ -v

test-unit: ## Run only validation/unit tests (no OmniFocus needed)
	$(PYTHON) -m pytest tests/test_validation.py -v

test-integration: ## Run integration tests (requires OmniFocus running)
	$(PYTHON) -m pytest tests/test_integration.py -v

build: clean ## Build sdist and wheel
	$(PYTHON) -m build

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

check: lint test ## Lint + test

publish: build ## Upload to PyPI (requires twine or uv publish)
	$(PYTHON) -m twine upload dist/* || $(UV) publish
