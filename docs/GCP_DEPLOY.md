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
- GEMINI_SEMANTIC_ENABLED: optional, default `false`. Adds Gemini intent
  routing for every free-text chat message.
- GEMINI_PUBLIC_SEARCH_ENABLED: optional, default `false`. Adds a Google
  Search grounded answer for policy questions internal documents cannot answer.
- GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS: default `10` (allowed 5–45).
- AI_CHAT_TIMEOUT_SECONDS: default `30`. Total time for one chat request; all
  Gemini calls and citation checks in a request share this budget and fall
  back to a non-AI answer when it runs out.

### What is sent to Google

The two flags above do **not** turn off all data sent to Google. Setting
`GEMINI_ENABLED=true` on its own already enables these calls:

| Call | Sent to Gemini | Masking |
|---|---|---|
| Employee lookup (`interpret_employee_query`) | The chat message, **including the employee name or code** (needed to identify the person) | Emails, phone numbers |
| Intent classification (`classify_intent`) | The chat message | Emails, phones, dates, numbers, times, stated reasons, "my name is …" |
| Policy answer (`ground_policy_answer`) | The question plus **excerpts of internal policy documents** the user may read | Emails, phones, employee codes, common name patterns in the question |
| Report and date parsing | Date phrases and report types only | No free text |

`GEMINI_SEMANTIC_ENABLED=true` adds the full chat message for routing (emails
and phones masked). `GEMINI_PUBLIC_SEARCH_ENABLED=true` adds the policy
question to Google Search, with employee codes and common Vietnamese name
patterns masked. Name masking is best effort and **not** a complete PII
control: unusual names, nicknames or all-caps names without a middle name can
pass through. No employee records (balances, attendance, payroll) are ever
sent. Enable `GEMINI_ENABLED` only after a privacy review covering the table
above.

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
