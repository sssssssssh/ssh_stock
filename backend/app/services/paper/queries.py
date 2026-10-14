from sqlalchemy import func, select, text

from app.domain.decision.contracts import PaperError
from app.models.paper import (
    DecisionApprovalEvent,
    DecisionObservation,
    DecisionProposal,
    PaperAccount,
    PaperAccountEvent,
    PaperDayRun,
    PaperFill,
    PaperLedgerEntry,
    PaperNavDaily,
    PaperOrder,
    PaperOrderAttempt,
    PaperOutcomeReview,
    PaperPositionDaily,
)
from app.repositories.paper import PaperRepository
from app.services.paper.records import next_open, verify_record

COLLECTIONS = {
    "accounts": PaperAccount,
    "observations": DecisionObservation,
    "proposals": DecisionProposal,
    "approvals": DecisionApprovalEvent,
    "events": PaperAccountEvent,
    "runs": PaperDayRun,
    "days": PaperNavDaily,
    "orders": PaperOrder,
    "attempts": PaperOrderAttempt,
    "fills": PaperFill,
    "ledger": PaperLedgerEntry,
    "positions": PaperPositionDaily,
    "reviews": PaperOutcomeReview,
}


def schema_ready(db):
    return bool(db.scalar(text("SELECT to_regclass('public.paper_account') IS NOT NULL")))


def projection(row):
    data = verify_record(row)
    facts = dict(row.record_json["facts"])
    facts.pop("owner_user_id", None)
    for key in (
        "state",
        "status",
        "version",
        "reason_code",
        "activated_at",
        "error_code",
        "result_hash",
        "generation",
        "job_id",
    ):
        if hasattr(row, key):
            value = getattr(row, key)
            facts[key] = (
                value.isoformat()
                if hasattr(value, "isoformat")
                else (str(value) if key == "job_id" and value is not None else value)
            )
    return {
        **facts,
        "mode": "PAPER",
        "record_hash": row.record_hash,
        "schema_version": row.schema_version,
        "data": data,
    }


class PaperQueries:
    def __init__(self, db):
        self.db, self.repo = db, PaperRepository(db)

    def account(self, owner, account_id):
        row = self.repo.owned(PaperAccount, owner, account_id)
        result = projection(row)
        latest = self.db.scalar(
            select(func.max(PaperNavDaily.trade_date)).where(
                PaperNavDaily.account_id == account_id, PaperNavDaily.owner_user_id == owner
            )
        )
        try:
            day = next_open(self.db, latest) if latest else row.first_trade_date
            result["next_trade_date"] = day.isoformat()
            result["calendar_error"] = None
        except PaperError as exc:
            result["next_trade_date"], result["calendar_error"] = None, exc.code
        result["latest_trade_date"] = latest.isoformat() if latest else None
        return result

    def detail(self, owner, kind, row_id):
        return projection(self.repo.owned(COLLECTIONS[kind], owner, row_id))

    def page(
        self,
        owner,
        kind,
        *,
        account_id=None,
        limit=20,
        offset=0,
        start=None,
        end=None,
        state=None,
        stage=None,
        trade_date=None,
    ):
        if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
            raise PaperError("PAPER_PAGE_INVALID", status_code=422)
        if start and end and start > end:
            raise PaperError("PAPER_DATE_RANGE_INVALID", status_code=422)
        if account_id:
            self.repo.owned(PaperAccount, owner, account_id)
        model = COLLECTIONS[kind]
        filters = [model.owner_user_id == owner]
        if account_id:
            if hasattr(model, "account_id"):
                filters.append(model.account_id == account_id)
            elif model is DecisionObservation:
                filters.append(model.record_json["data"]["account_id"].astext == str(account_id))
        date_column = getattr(model, "trade_date", getattr(model, "signal_date", None))
        if model is DecisionProposal:
            date_column = (
                select(DecisionObservation.signal_date)
                .where(
                    DecisionObservation.id == model.observation_id,
                    DecisionObservation.owner_user_id == owner,
                )
                .scalar_subquery()
            )
        if date_column is None and model is PaperOrder:
            date_column = model.scheduled_date
        if date_column is None and model is PaperOutcomeReview:
            date_column = model.asof_date
        if date_column is not None:
            if start:
                filters.append(date_column >= start)
            if end:
                filters.append(date_column <= end)
            if trade_date:
                filters.append(date_column == trade_date)
        state_column = getattr(model, "state", getattr(model, "status", None))
        if state and state_column is not None:
            filters.append(state_column == state)
        if stage and model is DecisionProposal:
            filters.append(model.stage == stage)
        total = self.db.scalar(select(func.count()).select_from(model).where(*filters))
        sort = date_column if date_column is not None else model.created_at
        rows = list(
            self.db.scalars(
                select(model)
                .where(*filters)
                .order_by(sort.desc(), model.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return [projection(row) for row in rows], {"total": total, "limit": limit, "offset": offset}
