from app.services.action_execution_service import ActionExecutionService
from app.services.agent_service import AgentService
from app.services.digest_service import DigestService
from app.services.draft_service import DraftService
from app.services.gmail_service import GmailService
from app.services.pipeline_service import PipelineService
from app.services.telegram_bot_service import TelegramBotService
from app.services.telegram_link_service import TelegramLinkService
from app.services.telegram_orchestration_service import TelegramOrchestrationService
from app.services.telegram_service import TelegramService
from app.services.token_cipher import token_cipher


gmail_service = GmailService(token_cipher=token_cipher)
agent_service = AgentService()
digest_service = DigestService()
draft_service = DraftService(gmail_service=gmail_service)
telegram_service = TelegramService()
action_execution_service = ActionExecutionService(draft_service=draft_service)
pipeline_service = PipelineService(gmail_service=gmail_service, digest_service=digest_service)
telegram_link_service = TelegramLinkService()
telegram_orchestration_service = TelegramOrchestrationService(
    pipeline_service=pipeline_service,
    agent_service=agent_service,
    telegram_service=telegram_service,
    action_execution_service=action_execution_service,
)
telegram_bot_service = TelegramBotService(
    telegram_service=telegram_service,
    link_service=telegram_link_service,
    orchestration_service=telegram_orchestration_service,
)
