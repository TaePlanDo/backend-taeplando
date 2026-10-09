from sqlalchemy.orm import configure_mappers

from app.models import Base


def test_sqlalchemy_mappers_configure() -> None:
    """Keep ORM relationship configuration valid as models evolve."""

    configure_mappers()
    assert Base.metadata.tables
