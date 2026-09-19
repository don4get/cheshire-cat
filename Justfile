set dotenv-load := true
set shell := ["bash", "-c"]

default:
    @just --list

postgres:
    docker compose up -d postgres
    @until docker compose exec -T postgres pg_isready -U cat -d cheshire_cat >/dev/null 2>&1; do sleep 1; done
    @echo "PostgreSQL is ready on localhost:5432"

api: postgres
    uv run cheshire-cat api --host 127.0.0.1 --port 8000

dashboard: postgres
    #!/usr/bin/env bash
    set -euo pipefail
    api_pid=""
    cleanup() {
        if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null; then
            kill "$api_pid" 2>/dev/null || true
            wait "$api_pid" 2>/dev/null || true
        fi
    }
    trap cleanup EXIT INT TERM
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "Using the existing Cheshire Cat API on localhost:8000"
    else
        uv run cheshire-cat api --host 127.0.0.1 --port 8000 &
        api_pid=$!
        until curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do
            if ! kill -0 "$api_pid" 2>/dev/null; then
                wait "$api_pid"
            fi
            sleep 1
        done
        echo "Started the Cheshire Cat API on localhost:8000"
    fi
    cd dashboard
    CHESHIRE_CAT_API_URL=http://127.0.0.1:8000 dx serve --platform web --addr 127.0.0.1 --port 8080 --open false
