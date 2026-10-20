from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(create_engine(database_url))
