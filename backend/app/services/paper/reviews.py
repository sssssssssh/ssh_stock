from bisect import bisect_right
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.domain.decision.contracts import PaperError, checked_snapshot, content_hash
from app.models.market_data import TradeCalendar
from app.models.paper import (
    DecisionProposal,
    PaperAccount,
    PaperAccountEvent,
    PaperDayRun,
    PaperOutcomeReview,
)
from app.repositories.paper import PaperRepository
from app.services.decision.source import DecisionSourceReadiness
from app.services.paper.account_state import account_settings, mark_day_review
from app.services.paper.execution import decimal_or_none
from app.services.paper.records import (
    make_record,
    replay,
    request_hash,
    request_lock,
    utc_now,
    verify_record,
)
from app.services.portfolio.ledger_precision import ratio


class PaperReviews:
    def __init__(self, db, settings, *, clock=utc_now, commit_guard=None):
        self.db, self.settings, self.clock = db, settings, clock
        self.repo = PaperRepository(db)
        self.commit_guard = commit_guard or (lambda result: None)

    def create(self, owner, account_id, body):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        drift_date = None
        try:
            request_lock(self.db, owner, "account-event", body.request_id)
            digest = content_hash([str(account_id), request_hash(owner, "review", body)])
            existing = replay(
                self.repo.by_request(PaperAccountEvent, owner, body.request_id), digest
            )
            if existing:
                self.commit_guard(existing)
                self.db.commit()
                return existing
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            head = self.db.scalar(
                select(PaperDayRun).where(
                    PaperDayRun.account_id == account.id,
                    PaperDayRun.trade_date == body.asof_date,
                    PaperDayRun.owner_user_id == owner,
                    PaperDayRun.phase == "DAY_COMPLETED",
                    PaperDayRun.status == "SUCCESS",
                )
            )
            if head is None:
                raise PaperError("PAPER_ACCOUNT_SNAPSHOT_NOT_READY")
            verify_record(head)
            count = self.db.scalar(
                select(func.count())
                .select_from(DecisionProposal)
                .where(
                    DecisionProposal.account_id == account.id,
                    DecisionProposal.owner_user_id == owner,
                )
            )
            if count > self.settings.paper_config.decision.max_source_rows:
                raise PaperError("PAPER_REVIEW_CAPACITY_EXCEEDED")
            try:
                checked_snapshot(
                    {"schema_version": "m17-review-capacity-v1", "ids": ["0" * 36] * count},
                    limit_bytes=90000,
                )
            except PaperError as exc:
                raise PaperError("PAPER_REVIEW_CAPACITY_EXCEEDED") from exc
            proposals = list(
                self.db.scalars(
                    select(DecisionProposal)
                    .where(
                        DecisionProposal.account_id == account.id,
                        DecisionProposal.owner_user_id == owner,
                    )
                    .order_by(DecisionProposal.id)
                )
            )
            now, ids = self.clock(), []
            reader = DecisionSourceReadiness(self.db, account_settings(account, self.settings))
            frozen_proposals = [(proposal, verify_record(proposal)) for proposal in proposals]
            earliest = min(
                (
                    date.fromisoformat(frozen["candidate"]["trade_date"])
                    for _, frozen in frozen_proposals
                ),
                default=body.asof_date,
            )
            calendar = list(
                self.db.scalars(
                    select(TradeCalendar.cal_date)
                    .where(
                        TradeCalendar.is_open.is_(True),
                        TradeCalendar.cal_date > earliest,
                        TradeCalendar.cal_date <= body.asof_date,
                    )
                    .order_by(TradeCalendar.cal_date)
                    .limit(self.settings.paper_config.decision.max_source_rows + 1)
                )
            )
            if len(calendar) > self.settings.paper_config.decision.max_source_rows:
                raise PaperError("PAPER_REVIEW_CAPACITY_EXCEEDED")
            matured, codes_by_date = [], {}
            for proposal, frozen in frozen_proposals:
                signal = date.fromisoformat(frozen["candidate"]["trade_date"])
                index = bisect_right(calendar, signal) + body.window_days - 1
                if index >= len(calendar):
                    continue
                target = calendar[index]
                matured.append((proposal, frozen, signal, target))
                codes_by_date.setdefault(target, set()).add(proposal.ts_code)
            inputs = {}
            for target, codes in sorted(codes_by_date.items()):
                drift_date = target
                inputs[target] = reader.capture(
                    target,
                    cutoff=now,
                    market_codes=tuple(sorted(codes)),
                    benchmark_code=account.benchmark_code,
                )
                financial_head = self.db.scalar(
                    select(PaperDayRun).where(
                        PaperDayRun.account_id == account.id,
                        PaperDayRun.owner_user_id == owner,
                        PaperDayRun.trade_date == target,
                        PaperDayRun.phase == "DAY_COMPLETED",
                    )
                )
                if financial_head is not None and (
                    financial_head.status != "SUCCESS"
                    or financial_head.source_hash != inputs[target]["source_hash"]
                ):
                    raise PaperError("PAPER_SOURCE_DRIFT")
                drift_date = None
            for proposal, frozen, signal_date, target in matured:
                source = inputs[target]
                raw = source["execution_input"]["stock_daily"].get(proposal.ts_code, {})
                opening, close = decimal_or_none(raw.get("open")), decimal_or_none(raw.get("close"))
                baseline = Decimal(frozen["candidate"]["close"])
                available = close is not None and close > 0 and baseline > 0
                metrics = {
                    "signal_date": signal_date,
                    "target_date": target,
                    "window_days": body.window_days,
                    "signal_close": str(baseline),
                    "observed_open": opening,
                    "observed_close": close,
                    "forward_mark_return": ratio(close / baseline - 1) if available else None,
                    "open_to_close_mark_return": ratio(close / opening - 1)
                    if available and opening is not None and opening > 0
                    else None,
                    "stage": proposal.stage,
                    "proposal_state_at_review": proposal.state,
                    "action": proposal.action,
                    "counterfactual": proposal.state != "APPROVED" or proposal.action == "WATCH",
                    "included_in_nav": False,
                    "interpretation": "POST_HOC_MARK_ONLY_NON_CAUSAL",
                    "denominator": {"opportunities": 1, "valid_marks": int(available)},
                    "source_hash": source["source_hash"],
                    "proposal_hash": proposal.record_hash,
                }
                source_hash = content_hash(metrics)
                old = self.db.scalar(
                    select(PaperOutcomeReview).where(
                        PaperOutcomeReview.proposal_id == proposal.id,
                        PaperOutcomeReview.asof_date == body.asof_date,
                        PaperOutcomeReview.window_days == body.window_days,
                        PaperOutcomeReview.eval_version == "m17-outcome-mark-v1",
                    )
                )
                if old:
                    verify_record(old)
                    if old.source_snapshot_hash != source_hash:
                        raise PaperError("PAPER_REVIEW_SOURCE_DRIFT")
                    ids.append(str(old.id))
                    continue
                row = self.repo.add(
                    make_record(
                        PaperOutcomeReview,
                        owner,
                        f"{proposal.id}:{body.asof_date}:{body.window_days}:v1",
                        now=now,
                        data=metrics,
                        account_id=account.id,
                        proposal_id=proposal.id,
                        asof_date=body.asof_date,
                        window_days=body.window_days,
                        eval_version="m17-outcome-mark-v1",
                        source_snapshot_hash=source_hash,
                        status="READY" if available else "UNAVAILABLE",
                    )
                )
                ids.append(str(row.id))
            event = self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    body.request_id,
                    now=now,
                    data={
                        "kind": "PAPER_REVIEW_COMPLETED",
                        "review_ids": ids,
                        "asof_date": body.asof_date,
                        "window_days": body.window_days,
                        "included_in_nav": False,
                    },
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=body.request_id,
                    request_hash=digest,
                )
            )
            self.commit_guard(event)
            self.db.commit()
            return event
        except Exception as exc:
            self.db.rollback()
            if (
                drift_date is not None
                and isinstance(exc, PaperError)
                and (exc.code == "PAPER_SOURCE_DRIFT" or exc.code.startswith("SOURCE_"))
            ):
                account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
                mark_day_review(self.db, account.id, drift_date)
                self.db.commit()
            raise
