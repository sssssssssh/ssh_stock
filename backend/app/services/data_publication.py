"""Candidate patches are private; only one CAS transaction may change published tables.

No business calculation lives here. Session-private typed views let the existing
calculators read their own checkpoints without copying all published history.
"""

import json
from datetime import UTC, date, datetime
from functools import lru_cache
from time import monotonic
from uuid import UUID

from sqlalchemy import Integer, MetaData, String, func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter

from app.models import market_data as m
from app.models.data_publication import (
    DataPublication,
    DataPublicationRow,
    DataPublicationScope,
    DataPublicationSource,
)
from app.models.job import JobRun
from app.services.job_execution import JobCancelled, JobOwnershipLost, checkpoint
from app.services.job_guard import data_queue_identity, scheduler_setting

MODELS = (
    m.StockTradeStatusDaily,
    m.StockFactorDaily,
    m.MarketDaily,
    m.SectorFactorDaily,
    m.ThemeFactorDaily,
    m.StockStateDaily,
    m.StockOpportunityDaily,
    m.StrategySignal,
    m.SignalForwardEval,
    m.DataQualityDaily,
)
REGISTRY = {model.__tablename__: model for model in MODELS}
KEYS = {model.__tablename__: tuple(c.name for c in model.__table__.primary_key) for model in MODELS}
KEYS.update(
    strategy_signal=("trade_date", "ts_code", "signal_type", "algo_version"),
    signal_forward_eval=("signal_id", "eval_version", "entry_basis"),
    data_quality_daily=("trade_date", "dataset"),
)
CORE = set(REGISTRY) - {"signal_forward_eval", "data_quality_daily"}
RAW_QUALITY = {
    "stock_daily",
    "adj_factor",
    "daily_basic",
    "index_daily",
    "stock_st",
    "suspend_d",
    "stk_limit",
    "ths_theme_daily",
    "ths_theme_moneyflow",
    "ths_theme_limit",
    "stock_adj_factor",
    "stock_daily_basic",
    "stock_st_daily",
    "stock_suspend_daily",
    "stock_limit_daily",
    "theme_daily",
    "theme_moneyflow_daily",
    "theme_limit_daily",
    "ths_theme_member_snapshot",
    "ths_theme_catalog",
}


def _json(value):
    return json.loads(
        json.dumps(
            value,
            default=lambda x: x.isoformat() if isinstance(x, (date, datetime)) else str(x),
            allow_nan=False,
        )
    )


@lru_cache
def published_table(model):
    """The one stable published-slice resolver, including legacy NULL provenance."""
    return model.__table__.to_metadata(MetaData(), schema="public")


def workspace(db):
    return db.info.get("publication_workspace") if isinstance(db, Session) else None


class PublicationWorkspace:
    def __init__(self, db: Session, job: JobRun):
        self.db, self.job_id, self.token = db, job.id, job.execution_token
        self.original_bind = db.get_bind()
        self.connection = None
        self.ready = False

    def open(self):
        db = self.db
        db.commit()
        # Pin a physical connection across checkpoint commits. Never return a
        # connection carrying pg_temp candidate views to an ordinary reader.
        self.connection = self.original_bind.engine.connect()
        db.bind = self.connection
        db.info["publication_workspace"] = self
        db.info["calculation_job_id"] = self.job_id
        db.add(
            DataPublication(
                job_id=self.job_id,
                execution_token=self.token,
                state="PREPARING",
                identity=data_queue_identity(),
                row_counts={},
            )
        )
        db.flush()
        self.register_source(self.job_id)
        for name, model in REGISTRY.items():
            columns = []
            for col in model.__table__.columns:
                if col.name == "trade_date":
                    columns.append('s.trade_date AS "trade_date"')
                elif col.name == "ts_code":
                    columns.append('s.entity_key AS "ts_code"')
                else:
                    columns.append(f'r."{col.name}"')
            key = ",".join(f'p."{c}"' for c in KEYS[name])
            published_columns = ",".join(f'p."{c.name}"' for c in model.__table__.columns)
            # Names are solely from the static model registry; UUID is generated
            # by PostgreSQL-backed claim, never arbitrary user SQL.
            db.execute(
                text(f"""CREATE TEMP VIEW "{name}" AS
                SELECT {",".join(columns)} FROM public.data_publication_row s
                CROSS JOIN LATERAL jsonb_populate_record(NULL::public."{name}", s.row_data) r
                WHERE s.publication_id = '{self.job_id}'::uuid AND s.table_name = '{name}'
                  AND NOT s.is_deleted
                UNION ALL SELECT {published_columns} FROM public."{name}" p WHERE NOT EXISTS (
                  SELECT 1 FROM public.data_publication_row s
                  WHERE s.publication_id = '{self.job_id}'::uuid AND s.table_name = '{name}'
                    AND s.row_key = jsonb_build_array({key}))""")
            )
        self.db.execute(
            update(JobRun)
            .where(
                JobRun.id == self.job_id,
                JobRun.status == "RUNNING",
                JobRun.execution_token == self.token,
            )
            .values(
                job_metadata=JobRun.job_metadata.op("||")(
                    {"publication": {"state": "PREPARING", "identity": str(self.job_id)}}
                )
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        self.ready = True

    def close(self):
        db = self.db
        try:
            db.rollback()
            if self.connection is not None:
                for name in REGISTRY:
                    self.connection.execute(text(f'DROP VIEW IF EXISTS pg_temp."{name}"'))
                self.connection.commit()
        except Exception:
            if self.connection is not None:
                self.connection.invalidate()
            raise
        finally:
            if self.connection is not None:
                self.connection.close()
            db.bind = self.original_bind
            db.info.pop("publication_workspace", None)
            db.info.pop("calculation_job_id", None)

    def register_source(self, identity):
        owner = self.db.get(JobRun, identity)
        if owner is None or (owner.id != self.job_id and owner.parent_job_id != self.job_id):
            raise JobOwnershipLost("PUBLICATION_SOURCE_NOT_OWNED")
        statement = insert(DataPublicationSource).values(
            publication_id=self.job_id, source_job_id=identity, role="CANDIDATE"
        )
        self.db.execute(statement.on_conflict_do_nothing())

    def _lookup(self, model, payload, *, public=False):
        table = published_table(model) if public else model.__table__
        keys = KEYS[model.__tablename__]
        values = [tuple(row[k] for k in keys) for row in payload]
        condition = (
            table.c[keys[0]].in_([k[0] for k in values])
            if len(keys) == 1
            else tuple_(*(table.c[k] for k in keys)).in_(values)
        )
        selected = list(table.c)
        if public:
            selected.append(func.to_jsonb(table.table_valued()).label("_publication_base"))
        return {
            tuple(row[k] for k in keys): dict(row)
            for row in self.db.execute(select(*selected).where(condition)).mappings()
        }

    def upsert(
        self,
        model,
        payload,
        conflict_columns,
        update_columns=None,
        preserve_existing_on_null_columns=None,
        merge_json_columns=None,
    ):
        name = model.__tablename__
        if tuple(conflict_columns) != KEYS[name]:
            raise ValueError("PUBLICATION_CONFLICT_KEY_MISMATCH")
        source = self.db.info["calculation_job_id"]
        self.register_source(source)
        if name in CORE:
            self.db.execute(
                update(DataPublicationSource)
                .where(
                    DataPublicationSource.publication_id == self.job_id,
                    DataPublicationSource.source_job_id == source,
                )
                .values(validated_at=None, validation=None)
            )
        count = 0
        # Bound key lookups and JSON inserts; never load all historical A rows.
        for offset in range(0, len(payload), 500):
            batch = payload[offset : offset + 500]
            existing, bases = self._lookup(model, batch), self._lookup(model, batch, public=True)
            now = self.db.scalar(select(func.now()))
            new_ids = iter(())
            if "id" in model.__table__.c:
                missing = sum(tuple(row[k] for k in KEYS[name]) not in existing for row in batch)
                if missing:
                    new_ids = iter(
                        self.db.scalars(
                            text(
                                "SELECT nextval(pg_get_serial_sequence(:table_name, 'id')) "
                                "FROM generate_series(1, :amount)"
                            ),
                            {"table_name": f"public.{name}", "amount": missing},
                        )
                    )
            staged = []
            for row in batch:
                key = tuple(row[k] for k in KEYS[name])
                previous = existing.get(key, {})
                prepared = {}
                for col in model.__table__.columns:
                    if col.name in row:
                        value = row[col.name]
                    elif col.name == "id":
                        value = previous.get("id") if previous else next(new_ids)
                    elif col.default is not None and col.default.is_scalar:
                        value = col.default.arg
                    elif col.server_default is not None:
                        value = now
                    else:
                        value = None
                    # Existing INSERTs accept integral floating counters from
                    # pandas. JSON record input uses integer text syntax, so
                    # preserve the value with its actual column type (0.0→0),
                    # never round/truncate non-integral business values.
                    if (
                        isinstance(col.type, Integer)
                        and type(value) is float
                        and value.is_integer()
                    ):
                        value = int(value)
                    prepared[col.name] = value
                updates = (
                    update_columns
                    if update_columns is not None
                    else [
                        c.name
                        for c in model.__table__.columns
                        if not c.primary_key and c.name not in conflict_columns
                    ]
                )
                if previous:
                    final = dict(previous)
                    for col in updates:
                        value = prepared[col]
                        if col in (preserve_existing_on_null_columns or ()) and value is None:
                            value = previous.get(col)
                        if col in (merge_json_columns or ()) and previous.get(col) is not None:
                            value = {**previous[col], **(value or {})}
                        final[col] = value
                else:
                    final = prepared
                provenance = final.get("calc_run_id") or final.get("job_id") or source
                if UUID(str(provenance)) != source:
                    raise ValueError("PUBLICATION_SOURCE_MISMATCH")
                staged.append(
                    dict(
                        publication_id=self.job_id,
                        table_name=name,
                        row_key=_json(key),
                        row_data=_json(final),
                        base_row=(bases[key]["_publication_base"] if key in bases else None),
                        source_id=source,
                        is_deleted=False,
                        trade_date=final.get("trade_date"),
                        entity_key=final.get("ts_code"),
                    )
                )
            self._store(staged)
            count += len(batch)
        return count

    def _store(self, rows):
        if not rows:
            return
        # Deletion masks arrive in the old repository's key-sized chunks;
        # candidate rows carry more bind columns than those original keys.
        for offset in range(0, len(rows), 500):
            self._store_batch(rows[offset : offset + 500])

    def _store_batch(self, rows):
        statement = insert(DataPublicationRow).values(rows)
        self.db.execute(
            statement.on_conflict_do_update(
                index_elements=["publication_id", "table_name", "row_key"],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in ("row_data", "source_id", "is_deleted", "trade_date", "entity_key")
                },
            )
        )

    def delete_keys(self, model, keys):
        columns = KEYS[model.__tablename__]
        payload = [dict(zip(columns, key, strict=True)) for key in keys]
        bases = self._lookup(model, payload, public=True)
        self._store(
            [
                dict(
                    publication_id=self.job_id,
                    table_name=model.__tablename__,
                    row_key=_json(key),
                    row_data=None,
                    base_row=(bases[key]["_publication_base"] if key in bases else None),
                    source_id=self.db.info["calculation_job_id"],
                    is_deleted=True,
                    trade_date=dict(zip(columns, key, strict=True)).get("trade_date"),
                    entity_key=None,
                )
                for key in keys
            ]
        )

    def record_scope(self, model, filters):
        source = self.db.info["calculation_job_id"]
        self.register_source(source)
        self.db.execute(
            update(DataPublicationSource)
            .where(
                DataPublicationSource.publication_id == self.job_id,
                DataPublicationSource.source_job_id == source,
            )
            .values(validated_at=None, validation=None)
        )
        dates = []
        for expression in filters:
            for value in visitors.iterate(expression):
                if isinstance(value, BindParameter):
                    values = (
                        value.value if isinstance(value.value, (tuple, list)) else [value.value]
                    )
                    dates.extend(v for v in values if type(v) is date)
        self.db.add(
            DataPublicationScope(
                publication_id=self.job_id,
                table_name=model.__tablename__,
                source_id=source,
                start_date=min(dates) if dates else None,
                end_date=max(dates) if dates else None,
            )
        )


def record_validation(db, source_id, day, result):
    current = workspace(db)
    if current is None or source_id is None or result.has_error:
        return
    current.register_source(source_id)
    row = db.get(DataPublicationSource, (current.job_id, source_id))
    days = set((row.validation or {}).get("days", []))
    days.add(day.isoformat())
    row.validation = {**(row.validation or {}), "days": sorted(days)}
    row.validated_at = datetime.now(UTC)
    db.add(row)


def defer_dirty_resolution(db, ranges):
    current = workspace(db)
    if current is None:
        return False
    source = db.info["calculation_job_id"]
    current.register_source(source)
    row = db.get(DataPublicationSource, (current.job_id, source))
    validation = dict(row.validation or {})
    ids = set(validation.get("pending_dirty_ids", [])) | {item.id for item in ranges}
    row.validation = {**validation, "pending_dirty_ids": sorted(ids)}
    db.add(row)
    # Keep PROCESSING visible until root publication commits. In particular,
    # a successful catchup child cannot certify public A as repaired by B.
    return True


def _finish_publication_dirty(db, current, status):
    ids = {
        key
        for source in db.scalars(
            select(DataPublicationSource).where(
                DataPublicationSource.publication_id == current.job_id,
                DataPublicationSource.role == "CANDIDATE",
            )
        )
        for key in (source.validation or {}).get("pending_dirty_ids", [])
    }
    if not ids:
        return
    rows = list(
        db.scalars(
            select(m.DataDirtyRange)
            .where(m.DataDirtyRange.id.in_(ids))
            .order_by(m.DataDirtyRange.id)
            .with_for_update()
        )
    )
    if status == "SUCCESS" and (
        len(rows) != len(ids) or any(row.status != "PROCESSING" for row in rows)
    ):
        raise ValueError("PUBLICATION_DIRTY_STATE_CHANGED")
    now = datetime.now(UTC)
    for row in rows:
        if row.status != "PROCESSING":
            continue  # Existing cancellation/failure cleanup already owns it.
        row.processing_started_at = None
        if status == "SUCCESS":
            row.status, row.resolved_at, row.last_error = "RESOLVED", now, None
        elif status == "CANCELLED":
            row.status, row.resolved_at = "OPEN", None
        else:
            row.status, row.last_failed_at = "FAILED", now
            row.retry_count = int(row.retry_count or 0) + 1
            row.last_error = "PUBLICATION_NOT_COMPLETED"
        db.add(row)


def route_upsert(db, model, payload, conflict_columns, **options):
    current = workspace(db)
    if current is None or model.__tablename__ not in REGISTRY:
        return None
    if model is m.DataQualityDaily:
        # Raw diagnostics remain Provider facts and must survive failed pulls.
        from app.repositories.upsert import upsert_rows

        raw = [row for row in payload if row.get("dataset") in RAW_QUALITY]
        derived = [row for row in payload if row.get("dataset") not in RAW_QUALITY]
        if raw:
            options_copy = dict(options)
            options_copy["_published_raw_quality"] = True
            upsert_rows(db, model, raw, conflict_columns, **options_copy)
        return len(raw) + (
            current.upsert(model, derived, conflict_columns, **options) if derived else 0
        )
    return current.upsert(model, payload, conflict_columns, **options)


def _qualified_keys(model, *, public_alias="p", candidate_alias="s", dialect):
    return " AND ".join(
        f'{public_alias}."{key}" = ({candidate_alias}.row_key ->> {index})::'
        f"{model.__table__.c[key].type.compile(dialect=dialect)}"
        for index, key in enumerate(KEYS[model.__tablename__])
    )


def _publishable_sql(name):
    # Validated *requested* dates only: warm-up calculations stay private.
    return (
        "s.publication_id = :root AND s.table_name = '" + name + "' AND EXISTS ("
        "SELECT 1 FROM public.data_publication_source v WHERE v.publication_id = :root "
        "AND v.source_job_id = s.source_id AND v.role = 'CANDIDATE' "
        "AND v.validated_at IS NOT NULL AND (v.validation->'days') ? s.trade_date::text)"
    )


def _verify_candidate(db, current):
    scopes = list(
        db.scalars(
            select(DataPublicationScope).where(
                DataPublicationScope.publication_id == current.job_id
            )
        )
    )
    sources = list(
        db.scalars(
            select(DataPublicationSource).where(
                DataPublicationSource.publication_id == current.job_id,
                DataPublicationSource.role == "CANDIDATE",
            )
        )
    )
    by_source = {row.source_job_id: row for row in sources}
    verified_sources = set()
    for source_id in {scope.source_id for scope in scopes}:
        source = by_source.get(source_id)
        job = db.get(JobRun, source_id)
        if source_id == current.job_id and job is not None and job.job_type == "catchup":
            # Raw refresh prepares trade-status rows for internal use. Only a
            # full recalculation child may validate/publish them, never the
            # catchup parent's partial preparatory scope.
            continue
        if source is None or source.validated_at is None or job is None:
            raise ValueError("PUBLICATION_QUALITY_NOT_VALIDATED")
        if source_id != current.job_id and job.status != "SUCCESS":
            raise ValueError("PUBLICATION_CHILD_NOT_SUCCESSFUL")
        verified_sources.add(source_id)
        days = {date.fromisoformat(day) for day in source.validation["days"]}
        metadata = dict(job.job_metadata or {})
        start = metadata.get("start") or metadata.get("trade_date")
        end = metadata.get("end") or metadata.get("trade_date")
        if start is None and job.target_trade_date:
            start = end = job.target_trade_date.isoformat()
        if start is None or end is None:
            raise ValueError("PUBLICATION_RANGE_NOT_PROVEN")
        expected = set(
            db.scalars(
                select(m.TradeCalendar.cal_date).where(
                    m.TradeCalendar.is_open.is_(True),
                    m.TradeCalendar.cal_date.between(
                        date.fromisoformat(start), date.fromisoformat(end)
                    ),
                )
            )
        )
        if not expected or days != expected:
            raise ValueError("PUBLICATION_VALIDATED_DATES_MISMATCH")
        for name in CORE:
            covered = {
                day
                for scope in scopes
                if scope.source_id == source_id
                and scope.table_name == name
                and scope.start_date
                and scope.end_date
                for day in days
                if scope.start_date <= day <= scope.end_date
            }
            if covered != days:
                raise ValueError(f"PUBLICATION_STAGE_INCOMPLETE:{name}")
        from app.core.config import get_settings
        from app.services.quality.opportunity_quality import check_opportunity_quality

        settings = get_settings()
        identity = data_queue_identity()
        for day in sorted(days):
            checkpoint()
            quality = check_opportunity_quality(
                db,
                day,
                strategy_hash=identity["analysis"],
                opportunity_hash=identity["opportunity"],
                algo_version=settings.algo_version,
                config=settings.opportunity_config,
            )
            if not quality.is_complete:
                raise ValueError("PUBLICATION_OPPORTUNITY_QUALITY_FAILED")
    if not scopes:
        raise ValueError("PUBLICATION_SCOPE_MISSING")
    from app.services.analysis_identity import (
        FACTOR_CALC_VERSION,
        MARKET_CALC_VERSION,
        OPPORTUNITY_CALC_VERSION,
        SECTOR_CALC_VERSION,
        SIGNAL_CALC_VERSION,
        THEME_CALC_VERSION,
        TRADE_STATUS_CALC_VERSION,
        TREND_CALC_VERSION,
    )

    versions = dict(
        zip(
            (model.__tablename__ for model in MODELS[:8]),
            (
                TRADE_STATUS_CALC_VERSION,
                FACTOR_CALC_VERSION,
                MARKET_CALC_VERSION,
                SECTOR_CALC_VERSION,
                THEME_CALC_VERSION,
                TREND_CALC_VERSION,
                OPPORTUNITY_CALC_VERSION,
                SIGNAL_CALC_VERSION,
            ),
            strict=True,
        )
    )
    identity = data_queue_identity()
    for name, version in versions.items():
        expected_hash = (
            identity["opportunity"]
            if name in {"theme_factor_daily", "stock_opportunity_daily"}
            else identity["analysis"]
        )
        count = db.scalar(
            select(func.count())
            .select_from(DataPublicationRow)
            .where(
                DataPublicationRow.publication_id == current.job_id,
                DataPublicationRow.table_name == name,
                DataPublicationRow.is_deleted.is_(False),
                DataPublicationRow.source_id.in_(verified_sources),
                (DataPublicationRow.row_data["calc_version"].as_string().is_distinct_from(version))
                | (
                    DataPublicationRow.row_data["config_hash"]
                    .as_string()
                    .is_distinct_from(expected_hash)
                )
                | (
                    DataPublicationRow.row_data["calc_run_id"]
                    .as_string()
                    .is_distinct_from(DataPublicationRow.source_id.cast(String))
                ),
            )
        )
        if count:
            raise ValueError(f"PUBLICATION_CANDIDATE_IDENTITY_MISMATCH:{name}")
        model = REGISTRY[name]
        extra_identity = []
        if "source_strategy_config_hash" in model.__table__.c:
            extra_identity.append(
                DataPublicationRow.row_data["source_strategy_config_hash"]
                .as_string()
                .is_distinct_from(identity["analysis"])
            )
        if "algo_version" in model.__table__.c:
            from app.core.config import get_settings

            extra_identity.append(
                DataPublicationRow.row_data["algo_version"]
                .as_string()
                .is_distinct_from(get_settings().algo_version)
            )
        for mismatch in extra_identity:
            if db.scalar(
                select(DataPublicationRow.publication_id)
                .where(
                    DataPublicationRow.publication_id == current.job_id,
                    DataPublicationRow.table_name == name,
                    DataPublicationRow.is_deleted.is_(False),
                    DataPublicationRow.source_id.in_(verified_sources),
                    mismatch,
                )
                .limit(1)
            ):
                raise ValueError(f"PUBLICATION_CANDIDATE_IDENTITY_MISMATCH:{name}")


def finish_publication(db, job, status):
    """Called inside the Job terminal CAS transaction; never commits itself."""
    current = workspace(db)
    if current is None or not current.ready:
        return None
    if job.id != current.job_id:
        return {"state": "PREPARING", "identity": str(current.job_id), "parent_owned": True}
    ledger = db.get(DataPublication, current.job_id)
    if ledger is None or ledger.execution_token != current.token or ledger.state != "PREPARING":
        raise JobOwnershipLost("PUBLICATION_OWNERSHIP_LOST")
    if status != "SUCCESS":
        _finish_publication_dirty(db, current, status)
        ledger.state = "ABORTED"
        db.add(ledger)
        return {"state": "ABORTED", "identity": str(current.job_id)}
    count = db.scalar(
        select(func.count())
        .select_from(DataPublicationRow)
        .where(DataPublicationRow.publication_id == current.job_id)
    )
    if not count and not db.scalar(
        select(DataPublicationScope.id)
        .where(DataPublicationScope.publication_id == current.job_id)
        .limit(1)
    ):
        ledger.state = "ABORTED"
        db.add(ledger)
        return {"state": "NO_CHANGES", "identity": str(current.job_id)}
    checkpoint()
    _verify_candidate(db, current)
    owner = db.scalar(
        select(JobRun)
        .where(JobRun.id == current.job_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if owner.execution_token != current.token or owner.status != "RUNNING":
        raise JobOwnershipLost("PUBLICATION_OWNERSHIP_LOST")
    if owner.cancel_requested:
        raise JobCancelled("JOB_CANCEL_REQUESTED")
    if ledger.identity != data_queue_identity():
        raise ValueError("JOB_CONFIG_CHANGED")
    ledger.publish_started_at = datetime.now(UTC)
    db.flush()
    started = monotonic()
    deadline_ms = int(scheduler_setting("data_publish_timeout_ms", 300000))

    def budget():
        remaining = deadline_ms - int((monotonic() - started) * 1000)
        if remaining <= 0:
            raise ValueError("PUBLICATION_TIME_BUDGET_EXCEEDED")
        db.execute(
            text("SELECT set_config('statement_timeout', :value, true)"), {"value": str(remaining)}
        )

    parameters = {"root": current.job_id}
    counts = {}
    total = 0
    for name in REGISTRY:
        budget()
        amount = db.scalar(
            text(
                "SELECT count(*) FROM public.data_publication_row s WHERE " + _publishable_sql(name)
            ),
            parameters,
        )
        counts[name] = amount
        total += amount
    if not total:
        ledger.state = "ABORTED"
        db.add(ledger)
        return {"state": "NO_CHANGES", "identity": str(current.job_id)}
    if total > int(scheduler_setting("data_publish_max_rows", 10000000)):
        raise ValueError("PUBLICATION_ROW_BUDGET_EXCEEDED")
    for name, model in REGISTRY.items():
        budget()
        predicate = _publishable_sql(name)
        join = _qualified_keys(model, dialect=db.get_bind().dialect)
        # Verify the published preimage has not changed behind the serial lane
        # (e.g. an unsupported legacy direct CLI or manual administrator write).
        changed = db.scalar(
            text(f"""SELECT EXISTS(SELECT 1
            FROM public.data_publication_row s LEFT JOIN public."{name}" p ON {join}
            WHERE {predicate} AND to_jsonb(p) IS DISTINCT FROM s.base_row)"""),
            parameters,
        )
        if changed:
            raise ValueError("PUBLICATION_BASE_CHANGED")
        keys = ",".join(f'p."{key}"' for key in KEYS[name])
        budget()
        db.execute(
            text(f"""INSERT INTO public.data_publication_preimage
            (publication_id, table_name, row_key, row_data)
            SELECT :root, '{name}', jsonb_build_array({keys}), to_jsonb(p)
            FROM public."{name}" p JOIN public.data_publication_row s ON {join}
            WHERE {predicate} ON CONFLICT DO NOTHING"""),
            parameters,
        )
        if name == "strategy_signal":
            # Preserve evaluation evidence before the existing signal FK's
            # ON DELETE CASCADE runs at publication, never at a checkpoint.
            budget()
            db.execute(
                text(f"""INSERT INTO public.data_publication_preimage
                (publication_id, table_name, row_key, row_data)
                SELECT :root, 'signal_forward_eval',
                  jsonb_build_array(e.signal_id,e.eval_version,e.entry_basis), to_jsonb(e)
                FROM public.signal_forward_eval e JOIN public.strategy_signal p ON e.signal_id=p.id
                JOIN public.data_publication_row s ON {join}
                WHERE {predicate} AND s.is_deleted ON CONFLICT DO NOTHING"""),
                parameters,
            )
        budget()
        db.execute(
            text(
                f'DELETE FROM public."{name}" p USING public.data_publication_row s '
                f"WHERE {predicate} AND s.is_deleted AND {join}"
            ),
            parameters,
        )
        columns = [col.name for col in model.__table__.columns]
        quoted = ",".join(f'"{col}"' for col in columns)
        updates = ",".join(
            f'"{col}"=EXCLUDED."{col}"'
            for col in columns
            if col not in {c.name for c in model.__table__.primary_key}
        )
        conflict = ",".join(f'"{col}"' for col in KEYS[name])
        budget()
        db.execute(
            text(f"""INSERT INTO public."{name}" ({quoted})
            SELECT {",".join(f'r."{col}"' for col in columns)}
            FROM public.data_publication_row s CROSS JOIN LATERAL
            jsonb_populate_record(NULL::public."{name}", s.row_data) r
            WHERE {predicate} AND NOT s.is_deleted
            ON CONFLICT ({conflict}) DO UPDATE SET {updates}"""),
            parameters,
        )
    # Retain real previous Job references without fabricating missing legacy jobs.
    budget()
    db.execute(
        text("""INSERT INTO public.data_publication_source
        (publication_id, source_job_id, role)
        SELECT DISTINCT :root, j.id, 'PREIMAGE' FROM public.data_publication_preimage p
        JOIN public.job_run j ON j.id = COALESCE(p.row_data->>'calc_run_id',
                                               p.row_data->>'job_id')::uuid
        WHERE p.publication_id = :root ON CONFLICT DO NOTHING"""),
        parameters,
    )
    _finish_publication_dirty(db, current, "SUCCESS")
    budget()
    ledger.state = "PUBLISHED"
    ledger.published_at = datetime.now(UTC)
    ledger.row_counts = counts
    db.add(ledger)
    return {
        "state": "PUBLISHED",
        "identity": str(current.job_id),
        "published_at": ledger.published_at.isoformat(),
        "row_counts": counts,
    }
