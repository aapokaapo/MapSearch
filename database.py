from typing import Generator

from sqlmodel import Session, create_engine

from config import database_path

DATABASE_URL = f"sqlite:///{database_path}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    from sqlmodel import SQLModel

    import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


init_db()
