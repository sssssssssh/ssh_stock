"""Root-owned rolling raw records, verified across checkpoint commits.

No cross-job cache or second connection. SHARE locks stabilize the existing
workspace view while evidence is checked and new tail rows are assembled.
Evidence survives eviction and is checked again under lock before publication.
"""

from datetime import timedelta

from sqlalchemy import Float, text
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.calculation_frame import read_calculation_frame
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calculation_memory import check_calculation_memory
from app.services.calculation_progress import ProgressStep
from app.services.data_publication import workspace
from app.services.factors.input_records import InputBlock, blocks_to_frame
from app.services.job_execution import JobOwnershipLost, checkpoint

TABLES = (
    "stock_daily", "stock_adj_factor", "stock_basic", "stock_trade_status_daily", "index_daily",
)
MAX_CACHE_BYTES = 1024 * 1024 * 1024


class FactorInputWindow:
    def __init__(self, db, job_id, settings, *, max_bytes=MAX_CACHE_BYTES):
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_CACHE_BYTES:
            raise ValueError("FACTOR_INPUT_MEMORY_BUDGET_INVALID")
        self.db, self.settings = db, settings
        self.root = workspace(db)
        if self.root is None or not self.root.ready:
            raise JobOwnershipLost("FACTOR_INPUT_WORKSPACE_REQUIRED")
        self.identity = (job_id, self.root.job_id, self.root.token,
                         (FACTOR_CALC_VERSION, TRADE_STATUS_CALC_VERSION),
                         analysis_strategy_hash(settings.strategy))
        if db.info.get("calculation_job_id") != job_id:
            raise JobOwnershipLost("FACTOR_INPUT_SOURCE_MISMATCH")
        self.max_bytes, self.bytes = max_bytes, 0
        self.peak_bytes = 0
        self.entries, self.evidence = {}, {}
        self.start = self.end = None
        self.closed = False
        self.read_transaction = None

    def _guard(self, *, check_source=False):
        checkpoint()
        if (workspace(self.db) is not self.root or not self.root.ready
                or self.db.get_bind() is not self.root.connection
                or self.root.token != self.identity[2]):
            raise JobOwnershipLost("FACTOR_INPUT_WORKSPACE_CHANGED")
        if (analysis_strategy_hash(self.settings.strategy) != self.identity[4]
                or (FACTOR_CALC_VERSION, TRADE_STATUS_CALC_VERSION) != self.identity[3]
                or self.settings.ab_merge_read_enabled
                or (check_source and self.db.info.get("calculation_job_id") != self.identity[0])):
            raise ValueError("FACTOR_INPUT_IDENTITY_CHANGED")

    def prepare(self, start, end):
        try:
            self._prepare(start, end)
        except BaseException:
            self.close()
            raise

    def _prepare(self, start, end):
        self._guard(check_source=True)
        if self.closed:
            raise ValueError("FACTOR_INPUT_WINDOW_CLOSED")
        if (end - start).days > 461 or end < start:
            raise ValueError("FACTOR_INPUT_WINDOW_UNBOUNDED")
        self.start = min(start, self.start) if self.start else start
        self.end = max(end, self.end) if self.end else end
        self.verify(capture=True)
        self.read_transaction = self.db.get_transaction()

    def verify(self, *, capture=False, publish_budget=None):
        progress = ProgressStep("factors.input_verify", "validate", batch_count=6)
        progress.report("query")
        try:
            self._verify(capture, publish_budget, progress)
        except BaseException as exc:
            progress.report("failed", log=True)
            if isinstance(exc, SQLAlchemyError):
                exc.calculation_query_name = "factors.input_verify"
            raise

    def _verify(self, capture, publish_budget, progress):
        self._guard()
        # Static table names only; locks are transaction-scoped and compatible
        # with ordinary/RR readers. No root row lock is taken here.
        names = ",".join(f'public."{name}"' for name in (*TABLES, "data_publication_row"))
        if publish_budget is not None:
            publish_budget()
        self.db.execute(text(f"LOCK TABLE {names} IN SHARE MODE"))
        actual = {}
        for index, name in enumerate(TABLES, 1):
            checkpoint()
            progress.report("query", batch_index=index)
            if publish_budget is not None:
                publish_budget()
            day = "NULL::date" if name == "stock_basic" else "trade_date"
            predicate = "TRUE" if name == "stock_basic" else "trade_date BETWEEN :lo AND :hi"
            actual[name] = dict(self.db.execute(text(f"""SELECT {day} AS day,
                encode(sha256(convert_to(string_agg(
                  encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex'),''
                  ORDER BY ts_code),'UTF8')),'hex')
                FROM public.\"{name}\" a WHERE {predicate} GROUP BY {day}"""),
                {"lo": self.start, "hi": self.end}).all())
            progress.report("batch_complete", batch_index=index, advanced=True)
        # All root status patches participate, including tombstones and malformed
        # redundant dates; a date predicate must never hide a mask from evidence.
        if publish_budget is not None:
            publish_budget()
        checkpoint()
        progress.report("query", batch_index=6)
        actual["candidate"] = self.db.scalar(text("""SELECT encode(sha256(convert_to(
            COALESCE(string_agg(encode(sha256(convert_to(to_jsonb(s)::text,'UTF8')),'hex'),''
            ORDER BY row_key),''),'UTF8')),'hex') FROM public.data_publication_row s
            WHERE publication_id=:root AND table_name='stock_trade_status_daily'"""),
            {"root": self.root.job_id})
        for name, previous in self.evidence.items():
            if name == "candidate":
                changed = actual[name] != previous
            else:
                old_start, old_end, fingerprints = previous
                observed = {day: digest for day, digest in actual[name].items()
                            if day is None or old_start <= day <= old_end}
                changed = observed != fingerprints
            if changed:
                raise ValueError("FACTOR_INPUT_SOURCE_CHANGED")
        if capture:
            self.evidence = {name: (self.start, self.end, value) if name != "candidate" else value
                             for name, value in actual.items()}
        progress.report("complete", batch_index=6, advanced=True)

    def _retain(self, block):
        check_calculation_memory()
        self.bytes += block.nbytes
        self.peak_bytes = max(self.peak_bytes, self.bytes)
        if self.bytes > self.max_bytes:
            raise MemoryError("FACTOR_INPUT_MEMORY_BUDGET_EXCEEDED")

    def read(self, statement, *, name, start=None, end=None, date_column=None):
        try:
            self._guard(check_source=True)
            if (self.closed or self.start is None
                    or self.db.get_transaction() is not self.read_transaction):
                raise ValueError("FACTOR_INPUT_WINDOW_NOT_PREPARED")
            if start is not None and (start < self.start or end > self.end):
                raise ValueError("FACTOR_INPUT_WINDOW_NOT_PREPARED")
            previous = self.entries.get(name)
            if start is None and previous is not None:
                blocks = previous[2]
            else:
                blocks = []
                if previous is not None:
                    lo, hi, old_blocks = previous
                    if lo <= start <= hi + timedelta(days=1) and end >= hi:
                        blocks = [cropped for block in old_blocks
                                  if (cropped := block.since(start)) is not None]
                        statement = statement.where(date_column > hi)
                # Recalculate accounting after eviction (all entries are bounded
                # by one rolling window, never the entire requested year).
                self.entries.pop(name, None)
                previous = old_blocks = None
                self.bytes = sum(block.nbytes for _, _, values in self.entries.values()
                                 for block in values)
                for block in blocks:
                    self._retain(block)
                float_columns = {column.key for column in statement.selected_columns
                                 if isinstance(column.type, Float)}

                def consume(batch):
                    block = InputBlock.from_records(batch, float_columns)
                    self._retain(block)
                    blocks.append(block)

                read_calculation_frame(self.db, statement, name=name, records_only=True,
                                       consume_batch=consume)
                self.entries[name] = (start, end, blocks)
            progress = ProgressStep("factors.input_frame", "read")
            progress.report("frame")
            check_calculation_memory(reserve=max(256 * 1024**2, self.bytes * 2))
            frame = blocks_to_frame(blocks)
            check_calculation_memory()
            # The two originally ordered inputs keep their exact code/date order.
            if not frame.empty and name in {"factors.stock_daily", "factors.index_daily"}:
                frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
            progress.report("complete", completed_rows=len(frame), advanced=True)
            return frame
        except BaseException:
            self.close()
            raise

    def close(self):
        self.entries.clear()
        self.bytes = 0
        self.closed = True
        self.read_transaction = None
