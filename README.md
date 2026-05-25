# Gmail Agent Assistant

Personal, Gmail-only assistant with Telegram-first operations for inbox triage, digesting, and draft suggestion under strict manual-send control.

## Explicit Safety Guarantee
This system never sends emails automatically.

- No email send endpoint is exposed.
- No `send_email` tool exists in backend services.
- Drafts can be generated and created in Gmail, but final send happens manually by the user in Gmail.

## Project Overview
The app is Telegram-first: users control sync, digesting, and approvals from Telegram commands and inline buttons. It syncs Gmail metadata/body into Postgres, runs structured AI analysis, tracks suggested actions in an audit log, and keeps email sending manual (draft-only automation).

## Architecture (Text Diagram)

```text
[Next.js Frontend]
   |
   | HTTP (REST)
   v
[FastAPI Backend]
   |-- /auth/*           -> Google OAuth flow
   |-- /emails/*         -> Gmail sync + stored email retrieval + analysis
   |-- /digests/*        -> digest generation + Telegram dispatch
   |-- /actions/*        -> approve/reject/execute suggested agent actions
   |-- /drafts/*         -> draft generation + create Gmail draft (no send)
   |-- /rules/*          -> user rule management
   |-- /telegram/*       -> webhook command handling + secure chat link + test endpoint
   |
   +--> [SQLAlchemy Models + Alembic Migrations] -> [Postgres]
   +--> [Celery Worker + Beat] <-> [Redis]
   +--> [OpenAI API (structured outputs)]
   +--> [Gmail API (read + draft only)]
   +--> [Telegram Bot API]
```

## Tech Stack
- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: Python + FastAPI
- Database: Postgres
- ORM/Migrations: SQLAlchemy + Alembic
- Background Jobs: Redis + Celery
- AI: OpenAI API (structured JSON outputs)
- Email: Gmail API
- Notifications/Control: Telegram Bot API

## Setup Instructions
1. Copy env template:
   - `cp .env.example .env` (PowerShell: `Copy-Item .env.example .env`)
2. Fill required values in `.env`:
   - Google OAuth credentials
   - OpenAI API key
   - Telegram bot token (+ optional bot username)
   - Telegram webhook base URL + secret token for webhook validation
   - Database URL
3. Install frontend dependencies:
   - `cd frontend && npm install`
4. Install backend dependencies:
   - `cd backend && pip install -r requirements.txt`

## Run

Docker Compose:
- `docker compose up --build`

Local split:
- Frontend: `cd frontend && npm run dev`
- Backend API: `cd backend && uvicorn app.main:app --reload`
- Celery worker: `cd backend && celery -A app.workers.tasks worker --loglevel=info`
- Celery beat: `cd backend && celery -A app.workers.tasks beat --loglevel=info`
- Migrations: `cd backend && alembic upgrade head`

## Current Scope
- Gmail read + draft creation integration (no auto-send)
- Google OAuth start/callback with encrypted token storage
- Telegram webhook command handling (`/start`, `/help`, `/sync`, `/digest`, `/pending`, `/rules`, `/rule add`, `/rule del`)
- Inline Telegram approve/reject callbacks for pending actions
- Hourly Telegram automation via Celery beat with scheduled idempotency
- Rule-aware AI analysis and draft generation

## Telegram Webhook Setup
- Set `TELEGRAM_WEBHOOK_BASE_URL` to your public HTTPS backend base URL (example: `https://agent.example.com`).
- Set `TELEGRAM_WEBHOOK_SECRET_TOKEN` to a strong random secret.
- On backend startup, the app auto-registers Telegram webhook URL as:
  - `<TELEGRAM_WEBHOOK_BASE_URL>/telegram/webhook`
- Telegram delivers webhook updates only to public HTTPS endpoints. Localhost is not reachable by Telegram unless exposed via a secure tunnel/reverse proxy.
- Verify webhook status with Telegram API:

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
