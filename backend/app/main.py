import logging
import time
from asyncio import to_thread
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.api import actions, auth, digests, drafts, emails, telegram
from app.db.migrations import run_db_migrations
from app.deps import telegram_service
from app.workers.tasks import run_direct_email_watcher_cycle, run_telegram_cycle

logger = logging.getLogger("email_agent")
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


async def run_inproc_scheduler_cycle() -> None:
    await to_thread(
        run_telegram_cycle,
        now_utc=datetime.now(timezone.utc),
        grace_minutes=settings.inproc_scheduler_grace_minutes,
    )


async def run_inproc_direct_email_watcher_cycle() -> None:
    await to_thread(
        run_direct_email_watcher_cycle,
        now_utc=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler: AsyncIOScheduler | None = None
    if settings.run_db_migrations_on_startup:
        try:
            run_db_migrations()
            logger.info("database_migrations_applied target=head")
        except Exception:
            logger.exception("database_migration_startup_failed")
            raise

    try:
        telegram_service.register_webhook_from_settings()
    except Exception:
        logger.exception("telegram_webhook_startup_registration_failed")

    if settings.inproc_scheduler_enabled:
        try:
            tick_seconds = max(settings.inproc_scheduler_tick_seconds, 1)
            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.add_job(
                run_inproc_scheduler_cycle,
                trigger="interval",
                seconds=tick_seconds,
                id="inproc-telegram-cycle",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            if settings.direct_email_watcher_enabled:
                watcher_seconds = max(settings.direct_email_watch_interval_minutes * 60, 60)
                scheduler.add_job(
                    run_inproc_direct_email_watcher_cycle,
                    trigger="interval",
                    seconds=watcher_seconds,
                    id="inproc-direct-email-watcher-cycle",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
            scheduler.start()
            logger.info(
                "inproc_scheduler_started tick_seconds=%s grace_minutes=%s direct_email_watcher_enabled=%s",
                tick_seconds,
                settings.inproc_scheduler_grace_minutes,
                settings.direct_email_watcher_enabled,
            )
        except Exception:
            scheduler = None
            logger.exception("inproc_scheduler_startup_failed")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("inproc_scheduler_stopped")


app = FastAPI(title="Gmail Agent Assistant", version="0.1.0", lifespan=lifespan)

def configure_cors(app_instance: FastAPI, origins: list[str]) -> None:
    if not origins:
        logger.info("cors_middleware_disabled reason=no_origins_configured")
        return

    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


configure_cors(app, settings.cors_origins)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete method=%s path=%s status=%s duration_ms=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "detail": exc.detail, "request_id": request_id},
    )


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "detail": exc.detail, "request_id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": exc.errors(), "request_id": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_exception request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Internal server error", "request_id": request_id},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(emails.router)
app.include_router(digests.router)
app.include_router(actions.router)
app.include_router(drafts.router)
app.include_router(telegram.router)
