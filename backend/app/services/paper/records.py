from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.domain.decision.contracts import PaperError, checked_snapshot, content_hash, stable_id
from app.models.market_data import TradeCalendar

MUTABLE = {
    "paper_account": {"state", "version", "activated_at"},
    "decision_proposal": {"state", "version"},
    "paper_order": {"status", "version", "reason_code"},
    "paper_day_run": {
        "status",
        "result_hash",
        "generation",
        "lease_owner",
        "lease_until",
        "job_id",
        "error_code",
    },
}
ENVELOPE = {"schema_version", "record_json", "record_hash"}


def utc_now():
    return datetime.now(UTC)


def source_value(value):
    if isinstance(value, float):
        value = Decimal(str(value))
        if not value.is_finite():
            raise PaperError("SOURCE_INVALID_NUMBER")
        return value
    if isinstance(value, dict):
        return {key: source_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [source_value(child) for child in value]
    return value


def _facts(row):
    excluded = ENVELOPE | MUTABLE.get(row.__tablename__, set())
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in excluded}


def make_record(model, owner_id, key, *, now, data=None, **values):
    row = model(
        id=stable_id(owner_id, model.__tablename__, key),
        owner_user_id=owner_id,
        created_at=now,
        **values,
    )
    for column in model.__table__.columns:
        if (
            getattr(row, column.name) is None
            and column.default is not None
            and column.default.is_scalar
        ):
            setattr(row, column.name, column.default.arg)
    row.schema_version = "m17-" + row.__tablename__.replace("_", "-") + "-v1"
    row.record_json, row.record_hash = checked_snapshot(
        {
            "schema_version": row.schema_version,
            "facts": _facts(row),
            "data": data or {},
        },
        limit_bytes=100000,
    )
    return row


def verify_record(row):
    if row is None:
        raise PaperError("PAPER_NOT_FOUND", status_code=404)
    version = "m17-" + row.__tablename__.replace("_", "-") + "-v1"
    if (
        row.schema_version != version
        or row.record_json.get("schema_version") != version
        or content_hash(row.record_json) != row.record_hash
        or content_hash(_facts(row)) != content_hash(row.record_json.get("facts"))
    ):
        raise PaperError("PAPER_RECORD_INTEGRITY_ERROR")
    return row.record_json["data"]


def request_lock(db, owner_id, operation, request_id):
    key = int.from_bytes(
        bytes.fromhex(content_hash([str(owner_id), operation, request_id]))[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def request_hash(owner_id, operation, body):
    return content_hash(
        {
            "owner": owner_id,
            "operation": operation,
            "body": body.model_dump(mode="python", exclude={"request_id"}),
        }
    )


def replay(row, digest):
    if row is not None:
        if row.request_hash != digest:
            raise PaperError("IDEMPOTENCY_CONFLICT")
        verify_record(row)
    return row


def next_open(db, after: date):
    day = db.scalar(
        select(TradeCalendar.cal_date)
        .where(
            TradeCalendar.is_open.is_(True),
            TradeCalendar.cal_date > after,
            TradeCalendar.exchange.in_(("SSE", "SZSE")),
        )
        .order_by(TradeCalendar.cal_date)
        .limit(1)
    )
    if day is None:
        raise PaperError("PAPER_CALENDAR_UNAVAILABLE")
    return day


def open_cutoff(day):
    return datetime.combine(day, time(9, 30), ZoneInfo("Asia/Shanghai")).astimezone(UTC)


def close_cutoff(day):
    return datetime.combine(day, time(15), ZoneInfo("Asia/Shanghai")).astimezone(UTC)
