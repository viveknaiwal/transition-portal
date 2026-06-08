# Transition Portal

Local Postgres-backed transition dashboard with a static frontend and Python API. The app is split into:

- `backend/` - Python HTTP API using local PostgreSQL via `psycopg2`
- `frontend/` - static HTML/CSS/JS dashboard

Important backend files:

- `backend/config.py` - environment-aware config loader
- `backend/constants.py` - roles, statuses, audit actions, reference catalogs, field lists
- `backend/models.py` - dataclass models for every Postgres table
- `backend/env/*.env` - environment defaults for `local`, `development`, `qa`, and `production`

No Supabase or third-party hosted database is used.

The UI uses the same Bifrost SSO pattern as the ITGC platform: Bifrost issues tokens in the browser, and the backend accepts the access token as `Authorization: Bearer ...`. For local development, `DEV_AUTH_ENABLED=true` exposes a local admin session button so the app can run without a QA redirect being registered.

## Local Postgres

Create a local database:

```bash
createdb transition_portal
```

If your Postgres user/password/database differs, set:

```bash
export DATABASE_URL="dbname=transition_portal"
```

The backend runs `backend/schema.sql` on startup. It creates required tables plus small reference catalogs for dropdown options; employee, case, role, upload, and audit records are read from local Postgres.

The backend loads config in this order:

1. `APP_ENV` or `ENV` decides which `backend/env/<env>.env` file to load.
2. `backend/.env` is loaded if present.
3. Real process environment variables win over file values.

Optional auth/config values live in `backend/.env.example`:

```bash
export APP_ENV="local"
export BIFROST_AUTH_API_URL="https://auth-service-qa.qac24svc.dev"
export BIFROST_CLIENT_ID="client_Q6G6tjO9NF8Ts2unKswoA"
export BIFROST_REDIRECT_URI="http://127.0.0.1:8501/login"
```

Darwinbox sync is backend-only. Configure these before using the sync action:

```bash
export DARWINBOX_USERNAME="..."
export DARWINBOX_PASSWORD="..."
export DARWINBOX_MASTER_API_KEY="..."
export DARWINBOX_DATASET_KEY="..."
export DARWINBOX_PAYROLL_API_KEY="..."
```

Approval uploads are stored under `backend/uploads/` and tracked in the `approval_uploads` table.

## Run

Terminal 1:

```bash
python3 backend/server.py
```

Terminal 2:

```bash
python3 frontend/server.py
```

Open:

```text
http://127.0.0.1:8501
```

Backend health:

```text
http://127.0.0.1:5050/api/health
```
