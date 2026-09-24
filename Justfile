set dotenv-load := true
set shell := ["bash", "-c"]

default:
    @just --list

postgres:
    #!/usr/bin/env bash
    set -euo pipefail
    # A PostgreSQL instance may already be running after a reboot (or may be
    # shared with another local compose project). In that case Docker cannot
    # claim 5432, but the dashboard can safely use the reachable configured DB.
    if python3 -c 'import psycopg; connection = psycopg.connect("postgresql://cat:meow@localhost:5432/cheshire_cat", connect_timeout=1); connection.close()' >/dev/null 2>&1; then
        echo "Using the existing PostgreSQL instance on localhost:5432"
    else
        timeout 30s docker compose up -d postgres || true
        until python3 -c 'import psycopg; connection = psycopg.connect("postgresql://cat:meow@localhost:5432/cheshire_cat", connect_timeout=1); connection.close()' >/dev/null 2>&1; do sleep 1; done
    fi
    echo "PostgreSQL is ready on localhost:5432"

api: postgres
    uv run cheshire-cat api --host 127.0.0.1 --port 8000

# Train and persist the investor bot, with a chronological 80/20 holdout.
research market="both": postgres
    uv run cheshire-cat research --market {{market}}

# Cost-aware walk-forward, uncertainty and stress diagnostics of saved research.
validate market="both": postgres
    uv run cheshire-cat validate-research --market {{market}}

# All registered Atlas trials, frozen selection, later-period evaluation and stress tests.
challenger market="both": postgres
    uv run cheshire-cat challenger --market {{market}}

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
