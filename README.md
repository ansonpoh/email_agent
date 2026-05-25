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
                        |-- /rules/*     -> user rule management
                        |-- /telegram/*  -> webhook + link token + link confirmation + test endpoint
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

## Telegram-First Setup/Test Flow
1. Connect Gmail account (one-time OAuth):
   - `POST /auth/google/start` to get `auth_url`
   - Open `auth_url` in a browser and complete consent
   - Google calls back to `GET /auth/google/callback`
2. Create Telegram link token:
   - `POST /telegram/link/start` with `user_id`
3. Link chat in Telegram:
   - Send `/start <token>` to your bot
4. Operate only through Telegram:
   - `/sync`
   - `/digest`
   - `/pending`
   - `/rules`
   - `/rule add <text>`
   - `/rule del <rule-id>`

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
- `GET /rules`
- `POST /rules`
- `DELETE /rules/{rule_id}`
- `POST /telegram/link`
- `POST /telegram/link/start`
- `POST /telegram/link/confirm`
- `POST /telegram/webhook`
- `POST /telegram/test`

## Security Notes
- Do not commit `.env`.
- Use env vars only; no hardcoded secrets.
- Restrict OAuth scopes to Gmail read/draft workflows.
- Keep audit log (`agent_actions`) for AI suggestions and decisions.
- Enforce manual approval for actionable suggestions.
- Maintain explicit prohibition on automatic email sending.
