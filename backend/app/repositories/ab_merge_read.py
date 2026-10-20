"""Explicit date-bounded overlay, initially ONLY factors.trade_status.

No candidate writes, commits, fallback, planner settings or business formulae.
Identifiers below are fixed model columns; all values are bound parameters.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.market_data import StockTradeStatusDaily
from app.repositories.calculation_frame import read_calculation_frame
from app.services.data_publication import workspace
from app.services.job_execution import JobOwnershipLost, checkpoint

FACTOR_COLUMNS = (
    "trade_date", "ts_code", "is_active", "is_suspended", "is_st", "st_status_unknown",
)


@dataclass(frozen=True)
class ReadWindow:
    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError("AB_READ_INVALID_WINDOW")


def trade_status_statement(*, candidate: bool, columns=FACTOR_COLUMNS):
    if not columns or any(c not in StockTradeStatusDaily.__table__.c for c in columns):
        raise ValueError("AB_READ_INVALID_COLUMNS")
    projection = ",".join(f'"{c}"' for c in columns)
    # Identity filtering is OUTSIDE the merge. In particular the anti-lookup
    # has NO identity/deletion predicate: wrong-version B and tombstones mask A.
    if candidate:
        union = """SELECT r.* FROM public.data_publication_row s
            CROSS JOIN LATERAL jsonb_populate_record(
                NULL::public.stock_trade_status_daily,s.row_data) r
            WHERE s.publication_id=:root AND s.table_name='stock_trade_status_daily'
              AND s.trade_date BETWEEN :lo AND :hi AND NOT s.is_deleted
            UNION ALL SELECT a.* FROM public.stock_trade_status_daily a
            WHERE a.trade_date BETWEEN :lo AND :hi AND NOT EXISTS (
                SELECT 1 FROM public.data_publication_row mask
                WHERE mask.publication_id=:root AND mask.table_name='stock_trade_status_daily'
                  AND mask.row_key=jsonb_build_array(a.trade_date,a.ts_code))"""
    else:
        union = "SELECT * FROM public.stock_trade_status_daily WHERE trade_date BETWEEN :lo AND :hi"
    return text(f"SELECT {projection} FROM ({union}) merged "
                "WHERE calc_version=:version AND config_hash=:hash ORDER BY ts_code,trade_date")


def _public_fingerprints(db, start, end):
    # Native built-in sha256; no extension/migration. All public business and
    # provenance columns, NULL and missing rows participate, not just version.
    return dict(db.execute(text("""SELECT trade_date,encode(sha256(convert_to(
        string_agg(encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex'),''
                   ORDER BY ts_code),'UTF8')),'hex') AS digest
        FROM public.stock_trade_status_daily a WHERE trade_date BETWEEN :lo AND :hi
        GROUP BY trade_date"""), {"lo": start, "hi": end}).all())


def verify_public_read_evidence(db: Session, current) -> None:
    """Must run under the public SHARE lock, also immediately before publication.

    Kept only for this root's life, never a reusable historical trust credential.
    A/B checkpoints still commit normally. Unsupported old writers between them
    cause a fail-closed abort rather than a mixed published result.
    """
    evidence = getattr(current, "ab_public_read_evidence", None)
    if not evidence:
        return
    actual = _public_fingerprints(db, min(evidence), max(evidence))
    if any(actual.get(day) != digest for day, digest in evidence.items()):
        raise ValueError("AB_READ_PUBLISHED_INPUT_CHANGED")


def _prepare_candidate_read(db, current, window):
    if not current.ready or db.get_bind() is not current.connection:
        raise JobOwnershipLost("AB_READ_WORKSPACE_NOT_PINNED")
    checkpoint()
    # These transaction-scoped locks allow all ordinary/RR readers. They only
    # serialize unsupported direct writers while windows are being assembled.
    # Never acquire a root row lock here (cancel endpoint must remain reachable).
    db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
    db.execute(text("LOCK TABLE public.data_publication_row IN SHARE MODE"))
    verify_public_read_evidence(db, current)
    # Validate ALL current B, including out-of-window tombstones. Otherwise a
    # corrupt redundant date could hide a mask from the bounded output branch.
    malformed = db.scalar(text("""SELECT EXISTS(SELECT 1 FROM public.data_publication_row s
        WHERE s.publication_id=:root AND s.table_name='stock_trade_status_daily' AND (
          s.trade_date IS NULL OR s.row_key->>1 IS NULL OR
          s.row_key IS DISTINCT FROM jsonb_build_array(s.trade_date,s.row_key->>1) OR
          (NOT s.is_deleted AND (
            s.entity_key IS DISTINCT FROM s.row_key->>1 OR
            s.row_data->>'trade_date' IS DISTINCT FROM s.trade_date::text OR
            s.row_data->>'ts_code' IS DISTINCT FROM s.entity_key OR
            nullif(s.row_data->>'calc_version','') IS NULL OR
            nullif(s.row_data->>'config_hash','') IS NULL))))"""), {"root": current.job_id})
    if malformed:
        raise ValueError("AB_READ_CANDIDATE_INVALID")
    actual = _public_fingerprints(db, window.start, window.end)
    from datetime import timedelta

    evidence = dict(getattr(current, "ab_public_read_evidence", {}))
    day = window.start
    while day <= window.end:
        evidence[day] = actual.get(day)
        day += timedelta(days=1)
    current.ab_public_read_evidence = evidence


class ABMergeReadRepository:
    def __init__(self, db: Session):
        self.db = db

    def read_trade_status(self, *, window: ReadWindow, calc_version: str,
                          config_hash: str) -> pd.DataFrame:
        current = workspace(self.db)
        if current is not None:
            _prepare_candidate_read(self.db, current, window)
        return read_calculation_frame(self.db, trade_status_statement(candidate=current is not None)
            .bindparams(lo=window.start, hi=window.end, version=calc_version, hash=config_hash,
                        **({"root": current.job_id} if current is not None else {})),
            name="factors.trade_status")
