# Gmail Agent Assistant

Backend-only, Telegram-operated Gmail assistant for inbox triage, digesting, and draft suggestion under strict manual-send control.

## Explicit Safety Guarantee
This system never sends emails automatically.

- No email send endpoint is exposed.
- No `send_email` tool exists in backend services.
- Drafts can be generated and created in Gmail, but final send happens manually by the user in Gmail.

## Architecture (Telegram-First)

```text
[Telegram User]
   |
   | Bot commands + inline callbacks
   v
[Telegram Bot API] -> [FastAPI Backend /telegram/webhook]
                        |-- /auth/*      -> Google OAuth flow
                        |-- /emails/*    -> Gmail sync + stored email retrieval + analysis
                        |-- /digests/*   -> digest generation + Telegram dispatch
                        |-- /actions/*   -> approve/reject/execute suggested actions
                        |-- /drafts/*    -> draft generation + create Gmail draft (no send)
                        |-- /telegram/*  -> webhook + Telegram test endpoint
                        |
                        +--> [SQLAlchemy + Alembic] -> [Postgres]
                        +--> [Celery Worker + Beat] <-> [Redis]
                        +--> [OpenAI API (structured outputs)]
                        +--> [Gmail API (read + draft only)]
```

## Tech Stack
- Backend: Python + FastAPI
- Database: Postgres
- ORM/Migrations: SQLAlchemy + Alembic
- Background Jobs: Redis + Celery
- AI: OpenAI API (structured JSON outputs)
- Email: Gmail API (read + draft only)
- Operations: Telegram Bot API

## Setup
1. Copy env template:
   - `cp .env.example .env` (PowerShell: `Copy-Item .env.example .env`)
2. Fill required values in `.env`:
   - Google OAuth credentials
   - OpenAI API key
   - Telegram bot token (+ optional bot username)
   - Telegram webhook base URL + secret token
   - Database URL
3. Install backend dependencies:
   - `cd backend && pip install -r requirements.txt`

## Run

Docker Compose:
- `docker compose up --build`

Local services:
- Backend API: `cd backend && uvicorn app.main:app --reload`
- Celery worker: `cd backend && celery -A app.workers.tasks worker --loglevel=info`
- Celery beat: `cd backend && celery -A app.workers.tasks beat --loglevel=info`
- Migrations: `cd backend && alembic upgrade head`

Notes:
- Backend startup runs `alembic upgrade head` automatically by default (`RUN_DB_MIGRATIONS_ON_STARTUP=true`).
- Set `RUN_DB_MIGRATIONS_ON_STARTUP=false` if you manage migrations separately in your deploy pipeline.

## Telegram-First Setup/Test Flow
1. Open chat with your bot and send `/start`.
2. Send `/connect` and click **Connect Gmail**.
3. Complete Google OAuth consent in browser.
4. Google calls back to `GET /auth/google/callback` and the backend auto-links your `telegram_chat_id`.
5. Operate through Telegram:
   - `/status`
   - `/sync`
   - `/today`
   - `/digest_schedule country <country>`
   - `/digest_schedule count <1-3>`
   - `/digest_schedule times <8am,1pm[,6pm]>`
   - `/digest_schedule status`
   - `/digest_schedule on`
   - `/digest_schedule off`
   - `/pending`

## Telegram Webhook
- Set `TELEGRAM_WEBHOOK_BASE_URL` to your public HTTPS backend URL.
- Backend startup auto-registers webhook at:
  - `<TELEGRAM_WEBHOOK_BASE_URL>/telegram/webhook`
- Localhost is not reachable by Telegram unless exposed via secure tunnel/reverse proxy.
- Verify webhook status:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

## Backend API Endpoints
- `GET /health`
- `POST /auth/google/start`
- `GET /auth/google/callback`
- `POST /emails/sync`
- `GET /emails`
- `GET /emails/{email_id}`
- `POST /emails/{email_id}/analyse`
- `POST /digests/generate`
- `GET /digests/latest`
- `POST /digests/{digest_id}/send-telegram`
- `GET /actions/pending`
- `POST /actions/{action_id}/approve`
- `POST /actions/{action_id}/reject`
- `POST /drafts/generate`
- `POST /drafts/{draft_id}/create-in-gmail`
- `POST /telegram/webhook`
- `POST /telegram/test`

## Security Notes
- Do not commit `.env`.
- Use env vars only; no hardcoded secrets.
- Restrict OAuth scopes to Gmail read/draft workflows.
- Keep audit log (`agent_actions`) for AI suggestions and decisions.
- Enforce manual approval for actionable suggestions.
- Maintain explicit prohibition on automatic email sending.
