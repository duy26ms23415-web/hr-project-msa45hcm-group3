# Deploy React + FastAPI to Cloud Run

Build context must be the repository root, with Dockerfile path `Dockerfile`.
The root Dockerfile builds `frontend/` with npm ci, installs `backend/`
dependencies, and serves both React and /api/v1 from FastAPI on the injected PORT.
No server.ts is required.

## Rebuild the current source

The failed builds fetched commit `fc24f97b688b50a921058a82477794cf479895b6`,
which has no root Dockerfile. Retrying that build reuses the old source.
Run the Cloud Build trigger against the latest `main` commit instead, or create
a new Cloud Run source deployment selecting branch `main`. Confirm FETCHSOURCE
shows the new commit, not fc24f97.

## Runtime configuration

Provide a reachable PostgreSQL database and configure:
- DATABASE_URL: `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB`
- SYNC_DATABASE_URL: `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DB`
- SECRET_KEY and KIOSK_API_SECRET_KEY: production secrets
- GEMINI_API_KEY: optional, for the AI provider
- GEMINI_ENABLED: set `true` only on revisions intended to call Gemini; default `false`
- GEMINI_MODEL_NAME: verify this exact identifier using the deployed key before use
- GEMINI_SEMANTIC_ENABLED: optional, default `false`. Sends free-text chat
  messages (emails and phone numbers masked) to Gemini for intent routing.
- GEMINI_PUBLIC_SEARCH_ENABLED: optional, default `false`. When internal
  documents cannot answer a policy question, sends the question to Gemini with
  Google Search grounding. Personal names are masked on a best-effort basis
  only; enable this only after privacy review.
- GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS: default `10`.
- AI_CHAT_TIMEOUT_SECONDS: default `30`. Total time for one chat request; all
  Gemini calls in a request share this budget and fall back when it runs out.

Use Secret Manager for secrets. Configure Cloud Run connectivity to the database.
The local docker-compose PostgreSQL service is not deployed by this image.
Run `alembic upgrade head` as a separate migration job with the same database
configuration before using the application. Seed demo data only when intended.

Before switching traffic to this revision, run `alembic upgrade head`
on the target database. Revision `c4d5e6f70819` creates
`hr_ai_role_scope_policies`, needed by AI chat and suggestions even
when Gemini is disabled. Verify migration, image digest, Secret Manager
references and runtime configuration in staging; retain a revision for
rollback. To inspect provider configuration from `backend/`, run
`python -B -m app.ai.providers.diagnose`; pass `--live` only after
billable test calls have been approved.

## Verify

- /health returns JSON (process health; it does not test database connectivity).
- / serves React; refreshing /login or /attendance still serves React.
- /api/v1/docs serves Swagger.
- Login and data operations require the configured database and migrations.

Local container check:
```bash
docker build -t hrms .
docker run --rm -p 8080:8080 --env-file backend/.env hrms
```
