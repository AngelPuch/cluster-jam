"""Own the app schema without creating tables during imports."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Map persistence names explicitly inside the service schema."""

    metadata = MetaData(schema="app")
