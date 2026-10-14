from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.domain.decision.contracts import PaperError, checked_snapshot, content_hash
from app.models.market_data import TradeCalendar
from app.models.paper import PaperAccount, PaperAccountEvent, PaperLedgerEntry, PaperOrder
from app.repositories.paper import PaperRepository
from app.services.paper.account_state import account_settings, source_contract
from app.services.paper.records import (
    make_record,
    next_open,
    open_cutoff,
    replay,
    request_hash,
    request_lock,
    utc_now,
    verify_record,
)


class PaperAccountApplication:
    def __init__(self, db, settings, *, clock=utc_now):
        self.db, self.settings, self.clock = db, settings, clock
        self.repo = PaperRepository(db)

    def create(self, owner, body):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        try:
            request_lock(self.db, owner, "account-create", body.request_id)
            digest = request_hash(owner, "account-create", body)
            existing = replay(self.repo.by_request(PaperAccount, owner, body.request_id), digest)
            if existing:
                self.db.commit()
                return existing
            request_lock(self.db, owner, "account-name", body.name)
            if self.db.scalar(
                select(PaperAccount.id).where(
                    PaperAccount.owner_user_id == owner, PaperAccount.name == body.name
                )
            ):
                raise PaperError("PAPER_ACCOUNT_NAME_CONFLICT")
            now = self.clock()
            today = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
            calendar = self.db.get(TradeCalendar, today)
            earliest = (
                today
                if (calendar and calendar.is_open and now < open_cutoff(today))
                else next_open(self.db, today)
            )
            first = body.first_trade_date or earliest
            calendar = self.db.get(TradeCalendar, first)
            if (
                first < earliest
                or not calendar
                or not calendar.is_open
                or calendar.exchange not in ("SSE", "SZSE")
            ):
                raise PaperError("PAPER_INCEPTION_DATE_INVALID", status_code=422)
            policy = self.settings.paper_config.policy
            if body.risk is not None:
                policy = policy.model_copy(update={"risk": body.risk})
            config, config_hash = checked_snapshot(
                {
                    "schema_version": "m17-account-config-v1",
                    "paper": policy.model_dump(mode="python"),
                    "execution": self.settings.execution_config.model_dump(mode="python"),
                    "accounting": self.settings.accounting_config.model_dump(mode="python"),
                    "decision": self.settings.paper_config.decision.model_dump(mode="python"),
                    "source_contract": source_contract(self.settings),
                }
            )
            account = self.repo.add(
                make_record(
                    PaperAccount,
                    owner,
                    body.request_id,
                    now=now,
                    name=body.name,
                    initial_cash=body.initial_cash,
                    benchmark_code=body.benchmark_code,
                    first_trade_date=first,
                    config_version=policy.version,
                    config_snapshot_json=config,
                    config_hash=config_hash,
                    request_id=body.request_id,
                    request_hash=digest,
                )
            )
            self.repo.add(
                make_record(
                    PaperLedgerEntry,
                    owner,
                    f"{account.id}:initial",
                    now=now,
                    account_id=account.id,
                    trade_date=first,
                    business_key="INITIAL_CASH",
                    entry_type="INITIAL_CASH",
                    cash_delta=body.initial_cash,
                    quantity_delta=0,
                )
            )
            self._event(
                owner,
                account,
                "create:" + content_hash(body.request_id),
                digest,
                None,
                "PAUSED",
                now,
                "ACCOUNT_CREATED",
            )
            self.db.commit()
            return account
        except Exception:
            self.db.rollback()
            raise

    def transition(self, owner, account_id, body, state):
        if state not in {"ACTIVE", "PAUSED", "CLOSED"}:
            raise PaperError("PAPER_STATE_INVALID", status_code=422)
        try:
            request_lock(self.db, owner, "account-event", body.request_id)
            digest = content_hash([str(account_id), state, request_hash(owner, state, body)])
            existing = replay(
                self.repo.by_request(PaperAccountEvent, owner, body.request_id), digest
            )
            if existing:
                self.db.commit()
                return existing
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            verify_record(account)
            if account.state == "CLOSED" or state == account.state:
                raise PaperError("PAPER_STATE_TRANSITION_INVALID")
            if state == "ACTIVE":
                if not self.settings.paper_config.enabled:
                    raise PaperError("PAPER_DISABLED", status_code=403)
                account_settings(account, self.settings)
            now, old = self.clock(), account.state
            account.state, account.version = state, account.version + 1
            if state == "ACTIVE" and account.activated_at is None:
                account.activated_at = now
            if state == "CLOSED":
                for order in self.db.scalars(
                    select(PaperOrder)
                    .where(
                        PaperOrder.account_id == account.id,
                        PaperOrder.owner_user_id == owner,
                        PaperOrder.status == "ORDER_PENDING",
                    )
                    .with_for_update()
                ):
                    verify_record(order)
                    order.status, order.reason_code = "CANCELLED", "ACCOUNT_CLOSED"
                    order.version += 1
            event = self._event(
                owner, account, body.request_id, digest, old, state, now, "ACCOUNT_STATE_CHANGED"
            )
            self.db.commit()
            return event
        except Exception:
            self.db.rollback()
            raise

    def _event(self, owner, account, request, digest, old, state, now, kind):
        return self.repo.add(
            make_record(
                PaperAccountEvent,
                owner,
                request,
                now=now,
                data={"kind": kind},
                account_id=account.id,
                from_state=old,
                to_state=state,
                request_id=request,
                request_hash=digest,
            )
        )
