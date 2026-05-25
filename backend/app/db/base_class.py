from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.db.schema import DB_SCHEMA


class Base(DeclarativeBase):
    metadata = MetaData(schema=DB_SCHEMA)
