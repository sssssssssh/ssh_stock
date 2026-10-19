import re
from time import monotonic

import pandas as pd
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import database_error_summary
from app.services.job_execution import checkpoint

FETCH_ROWS = 5000


def read_calculation_frame(db: Session, statement, *, name: str) -> pd.DataFrame:
    """Keep the original SELECT and transaction, but bound each network FETCH."""
    if len(name) > 80 or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?", name):
        raise ValueError("CALCULATION_READ_NAME_INVALID")
    checkpoint()
    started = last_log = monotonic()
    result = None
    rows = []
    logger.info("calculation read started query={}", name)
    try:
        result = db.execute(statement.execution_options(yield_per=FETCH_ROWS))
        for batch in result.mappings().partitions(FETCH_ROWS):
            checkpoint()
            rows.extend(batch)
            now = monotonic()
            if now - last_log >= 30:
                logger.info("calculation read progress query={} rows={} elapsed_seconds={:.1f}",
                            name, len(rows), now - started)
                last_log = now
        # Construct once, not one frame per FETCH, to retain whole-result dtype
        # inference (including all-NULL batches), ordering and empty-frame behavior.
        frame = pd.DataFrame(rows)
        logger.info("calculation read complete query={} rows={} elapsed_seconds={:.1f}",
                    name, len(rows), monotonic() - started)
        return frame
    except SQLAlchemyError as exc:
        exc.calculation_query_name = name
        logger.error("calculation read failed query={} rows={} elapsed_seconds={:.1f} error={}",
                     name, len(rows), monotonic() - started, database_error_summary(exc))
        raise
    finally:
        if result is not None:
            result.close()
