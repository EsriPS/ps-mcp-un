# PS-MCP developer Makefile.
#
# Single entry point for common workflows. Designed to also work cleanly from
# CI runners. All targets assume `uv` is on PATH.

.DEFAULT_GOAL := help

PYTHON ?= python
UV ?= uv

.PHONY: help install sync test test-integration test-all lint format build clean tag

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Sync the workspace (creates .venv, installs all packages + dev extras editable).
	$(UV) sync --all-packages --all-extras

sync: install ## Alias for `install`.

test: ## Run unit tests (excludes integration).
	$(UV) run pytest

test-integration: ## Run integration tests (require a running server).
	$(UV) run pytest -m integration

test-all: ## Run every test, including integration.
	$(UV) run pytest -m "integration or not integration"

coverage: ## Run unit tests with coverage report (term + html in htmlcov/).
	$(UV) run pytest \
		--cov=psmcp \
		--cov=psmcp_router_arcgis \
		--cov=psmcp_router_feature_service \
		--cov=psmcp_router_geoprocessing \
		--cov=psmcp_router_location_services \
		--cov=psmcp_router_mongo \
		--cov=psmcp_router_postgres \
		--cov-report=term-missing \
		--cov-report=html

lint: ## Lint with ruff.
	$(UV) run ruff check .

format: ## Format with ruff (in-place).
	$(UV) run ruff format .

build: ## Build a deployment package via the psmcp CLI.
	$(UV) run psmcp build

clean: ## Remove build artifacts and caches.
	rm -rf dist build .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +

tag: ## Tag and push a release. Usage: `make tag VERSION=0.2.0`.
ifndef VERSION
	$(error VERSION is required. Usage: make tag VERSION=0.2.0)
endif
	@if git rev-parse "v$(VERSION)" >/dev/null 2>&1; then \
		echo "Tag v$(VERSION) already exists"; exit 1; \
	fi
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	git push origin "v$(VERSION)"
	@echo "Tagged and pushed v$(VERSION). hatch-vcs will pick it up on the next build."

