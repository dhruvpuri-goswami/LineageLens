# LineageLens developer shortcuts. Run `make help`.
PY      ?= python3
VENV    ?= .venv
BIN     := $(VENV)/bin
COMPOSE ?= docker compose

.PHONY: help install dev test frontend build run docker-build up down logs audit clean

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n", $$1, $$2}'

install:         ## create .venv with locked runtime deps
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --require-hashes -r requirements.lock
	$(BIN)/pip install --no-deps -e .

dev: install     ## + test tools
	$(BIN)/pip install "pytest==9.1.1" "httpx==0.28.1"

test:            ## python + frontend tests
	$(BIN)/python -m pytest -q
	cd frontend && npm ci && npm run typecheck && npm test

frontend:        ## rebuild the UI into lineagelens/static
	cd frontend && npm ci && npm run build

run:             ## run locally on http://127.0.0.1:8765
	$(BIN)/lineagelens serve

docker-build:    ## build the Docker image
	$(COMPOSE) build

up:              ## start in Docker (http://127.0.0.1:8765)
	$(COMPOSE) up -d --build

down:            ## stop the container (data volume is kept)
	$(COMPOSE) down

logs:            ## follow container logs
	$(COMPOSE) logs -f

audit:           ## secret scan (needs gitleaks)
	gitleaks git --redact --no-banner .
	gitleaks dir --redact --no-banner .

clean:           ## remove build caches
	rm -rf build dist *.egg-info .pytest_cache frontend/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
