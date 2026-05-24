# Gmail Agent Assistant (MVP Skeleton)

Personal, Gmail-only, full-stack assistant for inbox triage, digesting, and draft suggestion with strict manual control.

## Explicit Safety Guarantee
This system never sends emails automatically.

- No email send endpoint is exposed.
- No `send_email` tool exists in backend services.
- Drafts can be generated and created in Gmail, but final send happens manually by the user in Gmail.

## Project Overview
The app syncs Gmail emails since the user last checked in, stores metadata/body in Postgres, runs AI-style structured analysis, tracks suggested actions in an audit log, and sends digest summaries to Telegram on explicit trigger.

## Architecture (Text Diagram)

```text
[Next.js Frontend]
   |
   | HTTP (REST)
   v
[FastAPI Backend]
   |-- /auth/*           -> Google OAuth flow (TODO wiring)
   |-- /emails/*         -> Gmail sync + stored email retrieval
   |-- /digests/*        -> digest generation + Telegram dispatch
   |-- /actions/*        -> approve/reject suggested agent actions
   |-- /drafts/*         -> draft generation + create Gmail draft (no send)
   |-- /rules/*          -> user rule management
   |-- /telegram/*       -> chat link + test endpoint
   |
   +--> [SQLAlchemy Models + Alembic Migrations] -> [Postgres (Neon in prod)]
   +--> [Celery Worker] <-> [Redis]
   +--> [OpenAI API (structured outputs) - TODO production wiring]
   +--> [Gmail API (read + draft only) - TODO production wiring]
   +--> [Telegram Bot API]
```

## Tech Stack
- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: Python + FastAPI
- Database: Postgres (Neon target, local Postgres in Docker Compose)
- ORM/Migrations: SQLAlchemy + Alembic
- Background Jobs: Redis + Celery
- AI: OpenAI API (structured JSON outputs)
- Email: Gmail API
- Notifications: Telegram Bot API

## Repository Structure

```text
.
+- frontend/
¦  +- app/
¦  ¦  +- page.tsx
¦  ¦  +- emails-summary/page.tsx
¦  ¦  +- suggested-actions/page.tsx
¦  ¦  +- draft-review/page.tsx
¦  ¦  +- settings/page.tsx
¦  +- components/app-shell.tsx
¦  +- lib/api.ts
+- backend/
¦  +- app/
¦  ¦  +- main.py
¦  ¦  +- api/
¦  ¦  +- services/
¦  ¦  +- models/
¦  ¦  +- schemas/
¦  ¦  +- db/
¦  ¦  +- workers/
¦  +- alembic/
¦  +- tests/
+- docker-compose.yml
+- .env.example
+- README.md
```

## Setup Instructions
1. Copy env template:
   - `cp .env.example .env` (or on PowerShell: `Copy-Item .env.example .env`)
2. Fill required values in `.env`:
   - Google OAuth credentials
   - OpenAI API key
   - Telegram bot token
   - Database URL (Neon recommended for real usage)
3. Install frontend dependencies:
   - `cd frontend && npm install`
4. Install backend dependencies:
   - `cd backend && pip install -r requirements.txt`

## Environment Variables
See `.env.example` for all variables.

Key ones:
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `TELEGRAM_BOT_TOKEN`
- `ENCRYPTION_KEY`

## Run with Docker Compose
1. Ensure `.env` exists.
2. Run:
   - `docker compose up --build`
3. Services:
   - Frontend: `http://localhost:3000`
   - Backend: `http://localhost:8000`
   - Redis: `localhost:6379`
   - Postgres: `localhost:5432`

## Run Frontend and Backend Separately

Frontend:
- `cd frontend`
- `npm run dev`

Backend:
- `cd backend`
- `uvicorn app.main:app --reload`

Worker:
- `cd backend`
- `celery -A app.workers.tasks worker --loglevel=info`

Migrations:
- `cd backend`
- `alembic upgrade head`

## Current MVP Scope
- Gmail-only integration scaffolding
- OAuth start/callback route placeholders
- Email sync/analyse/digest/draft/rules/telegram endpoint skeleton
- SQLAlchemy models for all required entities
- Alembic initial migration
- Typed Pydantic schemas for AI outputs
- Basic tests for schema and service logic

## Future Roadmap
- Real OAuth token exchange + token encryption at rest
- Real Gmail API sync with pagination and incremental history IDs
- OpenAI structured output calls with strong prompt templates and retries
- Per-user scheduling with Celery beat
- Rich frontend tables/forms/state management
- Full auth/session model for multi-user access control
- Production deployment manifests and observability

## Security Notes
- Do not commit `.env`.
- Use env vars only; no hardcoded secrets.
- Restrict OAuth scopes to Gmail read/draft workflows.
- Keep audit log (`agent_actions`) for all AI suggestions/decisions.
- Enforce manual approval for actionable suggestions.
- Maintain explicit prohibition on automatic email sending.

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
- `POST /telegram/test`

## Notes on Placeholders
Files include `TODO` markers where real credentials/API integrations are required:
- Google OAuth token exchange
- Gmail API read/draft calls
- OpenAI structured model calls
- Telegram live message dispatch
