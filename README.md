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

## Run (Desktop Self-Hosting)

1. Copy and configure env:
   - `Copy-Item .env.example .env`
   - Keep `DATABASE_URL` pointed to your existing cloud Postgres.
   - Set `TELEGRAM_WEBHOOK_BASE_URL=https://<your-stable-tunnel-domain>`.
   - Set `GOOGLE_REDIRECT_URI=https://<your-stable-tunnel-domain>/auth/google/callback`.
   - Keep `TELEGRAM_WEBHOOK_SECRET_TOKEN` set.
2. Start API, worker, and Redis:
   - `docker compose up -d --build`
3. Verify local health:
   - `curl.exe -sS http://localhost:8000/health`

### Optional: Run Cloudflare Tunnel in Docker
- Set `CLOUDFLARED_TUNNEL_TOKEN` in `.env`.
- Start tunnel profile:
  - `docker compose --profile tunnel up -d`

### Optional: Run Cloudflare Tunnel as Windows Service
- Install `cloudflared` and run (admin terminal):
  - `cloudflared.exe service install <TUNNEL_TOKEN>`
- This enables tunnel auto-start on reboot.

### Persistence on Reboot
- Containers use `restart: unless-stopped` in `docker-compose.yml`.
- Enable Docker Desktop auto-start on login.
- Ensure your tunnel client (Docker profile or Windows service) auto-starts.

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
   - `/today`
   - `/ask <question>`
   - `/followups`
   - `/due-today`
   - `/schedule country <country>`
   - `/schedule count <1-3>`
   - `/schedule times <8am,1pm[,6pm]>`
   - `/schedule status`
   - `/schedule on`
   - `/schedule off`

## Telegram Webhook
- Set `TELEGRAM_WEBHOOK_BASE_URL` to your public HTTPS backend URL.
- Backend startup auto-registers webhook at:
  - `<TELEGRAM_WEBHOOK_BASE_URL>/telegram/webhook`
- Localhost is not reachable by Telegram unless exposed via secure tunnel/reverse proxy.
- Telegram webhook delivery requires HTTPS and supported ports (`443`, `80`, `88`, `8443`).
- Verify webhook status:

```bash
curl.exe -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

## Cutover From Render to Desktop
1. Start local stack and tunnel, then confirm:
   - `curl.exe -sS http://localhost:8000/health`
   - `curl.exe -sS https://<your-stable-tunnel-domain>/health`
2. Check webhook now targets desktop domain:
   - `curl.exe -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"`
   - Confirm `url` is `https://<your-stable-tunnel-domain>/telegram/webhook`.
3. Run Telegram checks:
   - `/start`, `/status`, `/today`
4. Run OAuth check:
   - `/connect`, complete login, verify callback success page and chat link.
5. Disable/scale down Render service after verification to avoid dual-processing.

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
- `POST /actions/{action_id}/approve`
- `POST /actions/{action_id}/reject`
- `POST /drafts/generate`
- `POST /drafts/{draft_id}/create-in-gmail`
- `POST /telegram/webhook`
- `POST /telegram/test`

## Follow-up Tracking
- The assistant extracts commitments/tasks from analyzed emails and stores open follow-up items.
- Use `/followups` to list unresolved follow-up items.
- Use `/due-today` to show follow-ups due in your current timezone day.
- Optional proactive reminders:
  - `FOLLOWUP_REMINDERS_ENABLED=true`
  - `FOLLOWUP_REMINDER_LEAD_MINUTES=60`
  - `FOLLOWUP_REMINDER_COOLDOWN_HOURS=6`

## Security Notes
- Do not commit `.env`.
- Use env vars only; no hardcoded secrets.
- Restrict OAuth scopes to Gmail read/draft workflows.
- Keep audit log (`agent_actions`) for AI suggestions and decisions.
- Enforce manual approval for actionable suggestions.
- Maintain explicit prohibition on automatic email sending.
