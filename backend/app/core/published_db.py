"""One repeatable public snapshot per reader, separate from auth/write transactions."""

from contextlib import contextmanager

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db


@contextmanager
def published_snapshot(db):
    if (
        not isinstance(db, Session)
        or db.get_bind().dialect.name != "postgresql"
        or db.info.get("publication_workspace")
        or db.info.get("published_snapshot")
    ):
        yield db
        return
    with Session(bind=db.get_bind().engine, expire_on_commit=False) as reader:
        reader.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        reader.execute(text("SET TRANSACTION READ ONLY"))
        reader.info["published_snapshot"] = True
        yield reader


def get_published_db(db: Session = Depends(get_db)):
    with published_snapshot(db) as reader:
        yield reader
