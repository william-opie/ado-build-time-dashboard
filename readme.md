# Azure DevOps Build Time Dashboard

This FastAPI application surfaces Azure DevOps build durations, statuses, and links with lightweight filtering and pagination. The backend caches Azure DevOps responses, enforces rate limits, and validates Personal Access Tokens (PATs) before serving a decoupled, accessible frontend.

## Features
- **Secure configuration** via `.env` and PAT validation to prevent accidental secrets in source control.
- **Server-side filtering** with wildcard support, paging, and timezone-aware timestamps.
- **Structured logging, caching, and rate limiting** for production-friendly operations.
- **Accessible frontend** served via static assets with ARIA-friendly spinners and error states.
- **Testable modules** separating Azure DevOps API access, caching, and utility helpers.

## Getting started

### 1. Clone & install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment
Copy the sample file and update secrets. The PAT must have **Build (Read)** rights and follow Azure's 52-character format.
```bash
cp .env.example .env
```
`.env` should include:
```
AZDO_ORG=your-org
AZDO_PROJECT=YourProject
AZDO_PAT=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Run locally
```bash
uvicorn main:app --reload --port 8000
```
Visit http://localhost:8000 to load the dashboard.

### Docker compose
```yaml
services:
  ado-build-time-dashboard:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
```

## Testing
```bash
pytest
```

## Development tips
- Update `static/` and `templates/` for UI work—no backend changes required.
- Use `tests/` for fast unit coverage (mocks are included for the API client).
- Structured logs (JSON) are emitted to stdout; tail them with `jq` for readability.
- Respect the rate limiter when adding synthetic load; override via `AZDO_RATE_LIMIT_*` if necessary.

## Troubleshooting
- **429 responses** indicate the rate limiter is protecting the service; wait a moment before retrying.
- **502 responses** usually mean the PAT lacks permissions or the project/org names are incorrect.
- **Timezone conversions** rely on IANA names. Invalid names fall back to UTC.
