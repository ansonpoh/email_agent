from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings


def run_db_migrations() -> None:
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini = project_root / "alembic.ini"
    alembic_dir = project_root / "alembic"

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_dir))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
