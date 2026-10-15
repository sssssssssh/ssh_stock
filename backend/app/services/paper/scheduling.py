from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.config import get_settings
from app.domain.decision.account_requests import AdvancePaperAccount
from app.domain.decision.contracts import PaperError, content_hash
from app.domain.decision.requests import CreateObservation
from app.models.market_data import TradeCalendar
from app.models.paper import PaperAccount, PaperAccountEvent, PaperDayRun, PaperNavDaily
from app.repositories.paper import PaperRepository
from app.services.decision.source import DecisionSourceReadiness
from app.services.paper.account_state import account_settings, mark_day_review
from app.services.paper.queue import PaperQueue
from app.services.paper.records import (
    close_cutoff,
    make_record,
    next_open,
    request_lock,
    utc_now,
    verify_record,
)


def run_scheduled_paper(db, target_date, *, settings=None, clock=utc_now):
    settings = settings or get_settings()
    config = settings.paper_config
    result = {"queued": 0, "blocked": 0}
    if not config.enabled or not (config.auto_advance or config.decision.daily_observation_enabled):
        return result
    now = clock()
    if now.astimezone(ZoneInfo("Asia/Shanghai")).date() != target_date or now < close_cutoff(
        target_date
    ):
        return result
    calendar = db.get(TradeCalendar, target_date)
    if calendar is None or not calendar.is_open or calendar.exchange not in ("SSE", "SZSE"):
        return result
    accounts = list(
        db.scalars(
            select(PaperAccount)
            .where(PaperAccount.state == "ACTIVE")
            .order_by(PaperAccount.id)
            .limit(config.decision.max_source_rows + 1)
        )
    )
    if len(accounts) > config.decision.max_source_rows:
        raise PaperError("PAPER_SCHEDULER_CAPACITY_EXCEEDED")
    for account in accounts:
        drift_date = None
        try:
            verify_record(account)
            reader = DecisionSourceReadiness(db, account_settings(account, settings))
            latest = db.scalar(
                select(func.max(PaperNavDaily.trade_date)).where(
                    PaperNavDaily.account_id == account.id,
                    PaperNavDaily.owner_user_id == account.owner_user_id,
                )
            )
            if latest is not None:
                drift_date = latest
                frozen = db.scalar(
                    select(PaperNavDaily).where(
                        PaperNavDaily.account_id == account.id,
                        PaperNavDaily.trade_date == latest,
                    )
                )
                verify_record(frozen)
                current = reader.capture(latest, cutoff=now)
                head = db.scalar(
                    select(PaperDayRun).where(
                        PaperDayRun.account_id == account.id,
                        PaperDayRun.trade_date == latest,
                        PaperDayRun.phase == "DAY_COMPLETED",
                    )
                )
                if (
                    head is None
                    or head.status != "SUCCESS"
                    or frozen.source_hash != current["source_hash"]
                ):
                    raise PaperError("PAPER_SOURCE_DRIFT")
                drift_date = None
            expected = next_open(db, latest) if latest else account.first_trade_date
            reader.capture(target_date, cutoff=now)
            queue = PaperQueue(db, settings, clock=clock)
            if config.auto_advance and expected <= target_date:
                if expected != target_date:
                    raise PaperError("PAPER_DAY_GAP")
                body = AdvancePaperAccount(
                    request_id=f"scheduler:daily:{account.id}:{target_date}",
                    trade_date=target_date,
                )
                queued = queue.advance(account.owner_user_id, account.id, body, source="scheduler")
                result["queued"] += queued.status == "QUEUED"
            if config.decision.daily_observation_enabled:
                completed = latest == target_date or target_date < account.first_trade_date
                if completed:
                    body = CreateObservation(
                        request_id=f"scheduler:observe:{account.id}:{target_date}",
                        signal_date=target_date,
                        account_id=account.id,
                    )
                    queued = queue.observation(account.owner_user_id, account.id, body)
                    result["queued"] += queued.status == "QUEUED"
        except PaperError as exc:
            db.rollback()
            result["blocked"] += 1
            _blocked(db, account.owner_user_id, account.id, target_date, exc.code, now, drift_date)
    return result


def _blocked(db, owner, account_id, day, code, now, drift_date):
    key = "scheduler-blocked:" + content_hash([str(account_id), day, code])
    request_lock(db, owner, "account-event", key)
    repo = PaperRepository(db)
    account = repo.owned(PaperAccount, owner, account_id, lock=True)
    if drift_date is not None:
        mark_day_review(db, account.id, drift_date)
    if repo.by_request(PaperAccountEvent, owner, key) is None:
        repo.add(
            make_record(
                PaperAccountEvent,
                owner,
                key,
                now=now,
                data={"kind": "PAPER_SCHEDULER_BLOCKED", "trade_date": day, "reason_code": code},
                account_id=account.id,
                from_state=account.state,
                to_state=account.state,
                request_id=key,
                request_hash=content_hash([str(account_id), day, code]),
            )
        )
    db.commit()
