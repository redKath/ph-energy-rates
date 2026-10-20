from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.config import get_settings
from ph_energy_data.storage.db import make_session_factory


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return make_session_factory(get_settings().database_url)


def get_session() -> Iterator[Session]:
    with _session_factory()() as session:
        yield session
