from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.sync_user_emails")
def sync_user_emails(user_id: int) -> dict:
    # TODO: Invoke Gmail sync service with real OAuth credentials.
    return {"user_id": user_id, "status": "queued-mock"}


@celery_app.task(name="app.workers.tasks.generate_user_digest")
def generate_user_digest(user_id: int) -> dict:
    # TODO: Invoke digest generation pipeline.
    return {"user_id": user_id, "status": "queued-mock"}
