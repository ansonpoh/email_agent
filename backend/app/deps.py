from app.services.action_execution_service import ActionExecutionService
from app.services.agent_service import AgentService
from app.services.digest_service import DigestService
from app.services.direct_email_watcher_service import DirectEmailWatcherService
from app.services.draft_service import DraftService
from app.services.gmail_service import GmailService
from app.services.pipeline_service import PipelineService
from app.services.telegram_auth_state_service import TelegramAuthStateService
from app.services.telegram_bot_service import TelegramBotService
from app.services.telegram_direct_email_formatter import TelegramDirectEmailFormatter
from app.services.telegram_digest_formatter import TelegramDigestFormatter
from app.services.telegram_orchestration_service import TelegramOrchestrationService
from app.services.telegram_service import TelegramService
from app.services.token_cipher import token_cipher


gmail_service = GmailService(token_cipher=token_cipher)
agent_service = AgentService()
digest_service = DigestService()
draft_service = DraftService(gmail_service=gmail_service)
telegram_service = TelegramService()
telegram_digest_formatter = TelegramDigestFormatter()
telegram_direct_email_formatter = TelegramDirectEmailFormatter()
action_execution_service = ActionExecutionService(draft_service=draft_service)
pipeline_service = PipelineService(
    gmail_service=gmail_service,
    digest_service=digest_service,
    agent_service=agent_service,
)
direct_email_watcher_service = DirectEmailWatcherService(
    gmail_service=gmail_service,
    agent_service=agent_service,
    telegram_service=telegram_service,
    formatter=telegram_direct_email_formatter,
)
telegram_auth_state_service = TelegramAuthStateService()
telegram_orchestration_service = TelegramOrchestrationService(
    pipeline_service=pipeline_service,
    agent_service=agent_service,
    telegram_service=telegram_service,
    action_execution_service=action_execution_service,
    telegram_digest_formatter=telegram_digest_formatter,
)
telegram_bot_service = TelegramBotService(
    telegram_service=telegram_service,
    gmail_service=gmail_service,
    auth_state_service=telegram_auth_state_service,
    orchestration_service=telegram_orchestration_service,
)
