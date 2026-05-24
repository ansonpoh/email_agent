from app.services.agent_service import AgentService
from app.services.digest_service import DigestService
from app.services.draft_service import DraftService
from app.services.gmail_service import GmailService
from app.services.telegram_service import TelegramService


gmail_service = GmailService()
agent_service = AgentService()
digest_service = DigestService()
draft_service = DraftService(gmail_service=gmail_service)
telegram_service = TelegramService()
