from fastapi import FastAPI

from app.api import actions, auth, digests, drafts, emails, rules, telegram

app = FastAPI(title="Gmail Agent Assistant", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(emails.router)
app.include_router(digests.router)
app.include_router(actions.router)
app.include_router(drafts.router)
app.include_router(telegram.router)
app.include_router(rules.router)
