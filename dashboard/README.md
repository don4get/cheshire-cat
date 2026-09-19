# Cheshire Cat Dioxus dashboard

This is the Dioxus 0.7.10 replacement for the Python Dash frontend. It uses a
black-and-gold responsive terminal style inspired by `thesmartpdf`, loads live
data from the Python JSON API. It never substitutes invented prices,
fundamentals, portfolio values, or symbols: unavailable or empty PostgreSQL
data is shown as an explicit no-data state.

Run the API and dashboard in separate terminals:

```bash
uv run cheshire-cat api
cd dashboard
dx serve --platform web
```

The API is expected at the same origin in production (or behind a reverse
proxy). For local split-port development, proxy `/api` from the Dioxus dev
server to `http://127.0.0.1:8000`.
