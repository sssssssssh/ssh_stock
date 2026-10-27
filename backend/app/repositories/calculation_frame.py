import re
from time import monotonic

import pandas as pd
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import database_error_summary
from app.services.calculation_progress import ProgressStep
from app.services.job_execution import JobCancelled, checkpoint

FETCH_ROWS = 5000


def read_calculation_frame(
    db: Session, statement, *, name: str, records_only=False, check_batch=None, consume_batch=None,
) -> pd.DataFrame | list:
    """Keep the original SELECT and transaction, but bound each network FETCH."""
    if len(name) > 80 or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?", name):
        raise ValueError("CALCULATION_READ_NAME_INVALID")
    checkpoint()
    if consume_batch is not None and not records_only:
        raise ValueError("CALCULATION_READ_CONSUMER_REQUIRES_RECORD_MODE")
    started = last_log = monotonic()
    result = None
    rows = []
    row_count = 0
    progress = ProgressStep(name, "read")
    progress.report("query", log=True)
    logger.info("calculation read started query={}", name)
    try:
        result = db.execute(statement.execution_options(
            yield_per=FETCH_ROWS, calculation_query_name=name))
        from app.services.calculation_policy import active_policy

        policy = active_policy.get()
        fetched_at = monotonic()
        for index, batch in enumerate(result.mappings().partitions(FETCH_ROWS), start=1):
            if policy is not None:
                policy.observe_fetch(name, len(batch), monotonic()-fetched_at)
            checkpoint()
            if check_batch is not None:
                check_batch(batch)
            if consume_batch is not None:
                consume_batch(batch)
            else:
                rows.extend(batch)
            row_count += len(batch)
            progress.report("fetch", completed_rows=row_count, batch_index=index, advanced=True)
            now = monotonic()
            if now - last_log >= 30:
                logger.info("calculation read progress query={} rows={} elapsed_seconds={:.1f}",
                            name, row_count, now - started)
                last_log = now
            fetched_at = monotonic()
        # Construct once, not one frame per FETCH, to retain whole-result dtype
        # inference (including all-NULL batches), ordering and empty-frame behavior.
        progress.report("frame", completed_rows=row_count, log=True)
        frame = rows if records_only else pd.DataFrame(rows)
        progress.report("complete", completed_rows=row_count, advanced=True, log=True)
        logger.info("calculation read complete query={} rows={} elapsed_seconds={:.1f}",
                    name, row_count, monotonic() - started)
        return frame
    except SQLAlchemyError as exc:
        progress.report("failed", completed_rows=row_count, log=True)
        exc.calculation_query_name = name
        logger.error("calculation read failed query={} rows={} elapsed_seconds={:.1f} error={}",
                     name, row_count, monotonic() - started, database_error_summary(exc))
        raise
    finally:
        if result is not None:
            result.close()


def read_calculation_windows(db: Session, statements, *, name: str, observer=None) -> pd.DataFrame:
    """Windows only split SQL transport, NEVER dtype inference or calculation.

    All-or-error: no partial frame escapes on cancellation or SQL failure. The
    optional internal observer is for synthetic measurement, not a retry hook.
    """
    progress = ProgressStep(name, "read", batch_count=len(statements))
    rows = []
    for index, statement in enumerate(statements, 1):
        checkpoint()
        result = None
        started = monotonic()
        window_rows = 0
        first_5000 = None
        max_fetch = 0.0
        progress.report("query", batch_index=index, completed_rows=len(rows), log=True)
        try:
            result = db.execute(statement.execution_options(yield_per=FETCH_ROWS))
            mappings = result.mappings()
            first = mappings.fetchone()
            first_row = monotonic()-started if first is not None else None
            # Observe one delivered row, then put it back into the same 5000-row
            # client batches. yield_per still bounds the named cursor buffer;
            # dtype inference happens only after ALL windows have completed.
            pending = [first] if first is not None else []
            while True:
                fetch_started = monotonic()
                batch = pending + mappings.fetchmany(FETCH_ROWS-len(pending))
                pending = []
                elapsed = monotonic()-fetch_started
                if not batch:
                    break
                checkpoint()
                max_fetch = max(max_fetch, elapsed)
                rows.extend(batch)
                window_rows += len(batch)
                if first_5000 is None and window_rows >= FETCH_ROWS:
                    first_5000 = monotonic()-started
                if observer is not None:
                    observer({"event": "fetch", "window_index": index,
                              "seconds": elapsed, "rows": len(batch)})
                progress.report("fetch", batch_index=index, completed_rows=len(rows), advanced=True)
            metric = {"event": "window", "window_index": index,
                      "window_total": len(statements), "rows": window_rows,
                      "query_elapsed": monotonic()-started, "first_row_seconds": first_row,
                      "first_5000_seconds": first_5000, "max_fetch_seconds": max_fetch}
            if observer is not None:
                observer(metric)
            logger.info("calculation window query={} window={}/{} rows={} elapsed_seconds={:.3f} "
                        "first_row_seconds={} first_5000_seconds={} max_fetch_seconds={:.3f}",
                        name, index, len(statements), window_rows, metric["query_elapsed"],
                        first_row, first_5000, max_fetch)
            progress.report("batch_complete", batch_index=index,
                            completed_rows=len(rows), advanced=True, log=True)
        except JobCancelled:
            progress.report("cancelled", batch_index=index, completed_rows=len(rows), log=True)
            raise
        except SQLAlchemyError as exc:
            exc.calculation_query_name = name
            progress.report("failed", batch_index=index, completed_rows=len(rows), log=True)
            logger.error("calculation window failed query={} window={}/{} rows={} error={}",
                         name, index, len(statements), window_rows, database_error_summary(exc))
            raise
        finally:
            if result is not None:
                result.close()
    progress.report("frame", completed_rows=len(rows), log=True)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    progress.report("complete", completed_rows=len(rows), advanced=True, log=True)
    return frame
