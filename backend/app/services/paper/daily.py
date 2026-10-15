from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.domain.decision.contracts import PaperError, checked_snapshot, content_hash
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
    PaperPositionDaily,
)
from app.repositories.paper import PaperRepository
from app.services.decision.source import DecisionSourceReadiness
from app.services.paper.account_state import (
    account_settings,
    frozen_config,
    load_close,
    mark_day_review,
)
from app.services.paper.execution import (
    accounting_market,
    actual_risk,
    as_accounting_fill,
    decimal_or_none,
    opening_valuation,
    price_at_close,
    resolve_order,
)
from app.services.paper.records import (
    close_cutoff,
    make_record,
    next_open,
    open_cutoff,
    request_lock,
    utc_now,
    verify_record,
)
from app.services.portfolio.accounting import AccountingEngine, AccountingSourceError
from app.services.portfolio.ledger_precision import (
    adj_factor,
    money,
    normalize_snapshot_for_persistence,
    ratio,
)

ZERO = Decimal("0")


class PaperDailyApplication:
    """One bounded, atomic EOD replay; no backtest run or external execution calls."""

    def __init__(self, db, settings, *, clock=utc_now, fault_hook=None, commit_guard=None):
        self.db, self.settings, self.clock = db, settings, clock
        self.repo = PaperRepository(db)
        self.engine = AccountingEngine()
        self.fault_hook = fault_hook or (lambda phase: None)
        self.commit_guard = commit_guard or (lambda result: None)

    def run(self, owner, account_id, day, *, job_id=None):
        account, checkpoints, committed = None, [], False
        try:
            if not self.settings.paper_config.enabled:
                raise PaperError("PAPER_DISABLED", status_code=403)
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            verify_record(account)
            sealed = self.db.scalar(
                select(PaperDayRun).where(
                    PaperDayRun.account_id == account.id,
                    PaperDayRun.owner_user_id == owner,
                    PaperDayRun.trade_date == day,
                    PaperDayRun.phase == "DAY_COMPLETED",
                )
            )
            if sealed and sealed.status == "REVIEW_REQUIRED":
                raise PaperError("PAPER_SOURCE_DRIFT")
            if not sealed and account.state != "ACTIVE":
                raise PaperError("PAPER_ACCOUNT_NOT_ACTIVE")
            config = frozen_config(account)
            reader = DecisionSourceReadiness(self.db, account_settings(account, self.settings))
            now = self.clock()
            if now < close_cutoff(day):
                raise PaperError("SOURCE_EOD_NOT_READY")
            if day < account.first_trade_date:
                raise PaperError("PAPER_INCEPTION_DATE_INVALID")
            orders = list(
                self.db.scalars(
                    select(PaperOrder)
                    .where(
                        PaperOrder.account_id == account.id,
                        PaperOrder.owner_user_id == owner,
                        PaperOrder.scheduled_date == day,
                    )
                    .order_by(PaperOrder.side.desc(), PaperOrder.id)
                )
            )
            previous_day = self._previous_date(day)
            if next_open(self.db, previous_day) != day:
                raise PaperError("PAPER_DAY_GAP")
            if day != account.first_trade_date:
                previous_run = self.db.scalar(
                    select(PaperDayRun).where(
                        PaperDayRun.account_id == account.id,
                        PaperDayRun.trade_date == previous_day,
                        PaperDayRun.phase == "DAY_COMPLETED",
                        PaperDayRun.status == "SUCCESS",
                    )
                )
                if previous_run is None:
                    raise PaperError("PAPER_DAY_GAP")
                verify_record(previous_run)
            previous, contexts, previous_hash = load_close(self.db, account, previous_day)
            latest = self.db.scalar(
                select(func.max(PaperNavDaily.trade_date)).where(
                    PaperNavDaily.account_id == account.id,
                    PaperNavDaily.owner_user_id == owner,
                )
            )
            if sealed is None and latest is not None and latest != previous_day:
                raise PaperError("PAPER_DAY_GAP")
            self._verify_signals(owner, account, orders, reader, now)
            if previous_day >= account.first_trade_date:
                try:
                    previous_source = reader.capture(previous_day, cutoff=now)
                except PaperError:
                    self._mark_review(account.id, previous_day)
                    self.db.commit()
                    committed = True
                    raise
                previous_nav = self.db.scalar(
                    select(PaperNavDaily).where(
                        PaperNavDaily.account_id == account.id,
                        PaperNavDaily.trade_date == previous_day,
                    )
                )
                if previous_nav.source_hash != previous_source["source_hash"]:
                    self._mark_review(account.id, previous_day)
                    self.db.commit()
                    committed = True
                    raise PaperError("PAPER_SOURCE_DRIFT")
            codes = sorted({p.ts_code for p in previous.positions} | {o.ts_code for o in orders})
            source = reader.capture(
                day, cutoff=now, market_codes=codes, benchmark_code=account.benchmark_code
            )
            facts = source["execution_input"]
            if facts["calendar"]["previous_date"] != previous_day:
                raise PaperError("PAPER_SOURCE_DRIFT")
            source_hash = source["source_hash"]
            payload = {
                "config_hash": account.config_hash,
                "previous_snapshot_hash": previous_hash,
                "source_hash": source_hash,
                "execution_input": facts,
                "orders": [order.record_hash for order in orders],
            }
            _, input_hash = checked_snapshot(
                {"schema_version": "m17-day-input-v1", **payload}, limit_bytes=100000
            )
            if sealed:
                verify_record(sealed)
                if sealed.input_hash != input_hash or sealed.source_hash != source_hash:
                    raise PaperError("PAPER_SOURCE_DRIFT")
                if sealed.status != "SUCCESS" or sealed.result_hash != self._bundle(account, day):
                    raise PaperError("PAPER_LEDGER_INCONSISTENT")
                self.commit_guard(sealed)
                self.db.commit()
                return sealed
            if any(order.status != "ORDER_PENDING" for order in orders):
                raise PaperError("PAPER_ORDER_ALREADY_TERMINAL")
            working = self.engine.open_state(
                trade_date=day, initial_cash=account.initial_cash, previous_snapshot=previous
            )
            market = accounting_market(facts, codes)
            for order in orders:
                row = market[order.ts_code]
                if (
                    row.previous_adj_factor is None
                    or row.current_adj_factor is None
                    or row.previous_adj_factor != row.current_adj_factor
                ):
                    raise PaperError("CORPORATE_ACTION_UNSUPPORTED")
            try:
                self.engine.validate_start_of_day(working, market)
            except AccountingSourceError as exc:
                raise PaperError(
                    "CORPORATE_ACTION_UNSUPPORTED"
                    if "UNSUPPORTED" in exc.reason_code
                    else "SOURCE_NOT_READY"
                ) from exc
            for position in previous.positions:
                if adj_factor(market[position.ts_code].previous_adj_factor) != position.adj_factor:
                    raise PaperError("PAPER_SOURCE_DRIFT")
            opening_assets = opening_valuation(working, facts)
            for phase in ("EXECUTION", "CLOSE", "DAY_COMPLETED"):
                row = self.db.scalar(
                    select(PaperDayRun).where(
                        PaperDayRun.account_id == account.id,
                        PaperDayRun.trade_date == day,
                        PaperDayRun.phase == phase,
                    )
                )
                if row:
                    verify_record(row)
                    if row.input_hash != input_hash or row.status != "FAILED":
                        raise PaperError("PAPER_SOURCE_DRIFT")
                    row.status, row.generation, row.error_code = "RUNNING", row.generation + 1, None
                    row.job_id = job_id
                else:
                    row = make_record(
                        PaperDayRun,
                        owner,
                        f"{account.id}:{day}:{phase}",
                        now=now,
                        data={
                            "market_data_mode": config.policy.market_data_mode,
                            "previous_snapshot_hash": previous_hash,
                            "execution_mode": "PAPER_FORWARD_REPLAY_FROM_ARCHIVED_INPUTS"
                            if day < now.astimezone(ZoneInfo("Asia/Shanghai")).date()
                            else "PAPER_FORWARD_EOD",
                        },
                        account_id=account.id,
                        trade_date=day,
                        phase=phase,
                        status="RUNNING",
                        source_hash=source_hash,
                        input_hash=input_hash,
                        job_id=job_id,
                    )
                    self.repo.add(row)
                checkpoints.append(row)
            execution_run, close_run, completed = checkpoints
            turnover, trading_cost, new_codes = ZERO, ZERO, set()
            self.fault_hook("before_orders")
            for order in orders:
                plan = verify_record(order)
                context = plan["candidate"]
                prospective_contexts = (
                    {**contexts, order.ts_code: context} if order.side == "BUY" else dict(contexts)
                )
                decision, blocked = resolve_order(order, facts, working, config.execution)
                prospective = None
                if decision:
                    prospective, _ = self.engine.apply_fills(
                        working, [as_accounting_fill(decision, order.id)]
                    )
                    blocked = actual_risk(
                        decision=decision,
                        before=working,
                        after=prospective,
                        contexts=prospective_contexts,
                        facts=facts,
                        risk=config.policy.risk,
                        opening_assets=opening_assets,
                        turnover=turnover,
                        new_codes=new_codes,
                    )
                attempt = self.repo.add(
                    make_record(
                        PaperOrderAttempt,
                        owner,
                        f"{order.id}:{day}:1",
                        now=now,
                        data={
                            "order_hash": order.record_hash,
                            "market_data_mode": config.policy.market_data_mode,
                        },
                        account_id=account.id,
                        order_id=order.id,
                        trade_date=day,
                        attempt_no=1,
                        outcome="SKIPPED" if blocked else "FILLED",
                        reason_code=blocked,
                        market_snapshot_hash=content_hash(
                            {
                                key: value.get(order.ts_code)
                                for key, value in facts.items()
                                if isinstance(value, dict)
                            }
                        ),
                        execution_policy_version=config.policy.version,
                    )
                )
                order.status, order.reason_code = attempt.outcome, blocked
                order.version += 1
                if blocked:
                    continue
                before_position = next(
                    (p for p in working.positions if p.ts_code == order.ts_code), None
                )
                realized = (
                    ZERO
                    if order.side == "BUY"
                    else money(decision.cash_delta - before_position.avg_cost * order.quantity)
                )
                fee_json, _ = checked_snapshot(
                    {
                        "schema_version": "m17-paper-fees-v1",
                        "commission": decision.commission,
                        "stamp_tax": decision.stamp_tax,
                        "transfer_fee": decision.transfer_fee,
                        "slippage_cost": decision.slippage_cost,
                    },
                    limit_bytes=4096,
                )
                fill = self.repo.add(
                    make_record(
                        PaperFill,
                        owner,
                        str(attempt.id),
                        now=now,
                        data={
                            "realized_delta": realized,
                            "market_data_mode": config.policy.market_data_mode,
                        },
                        account_id=account.id,
                        order_id=order.id,
                        attempt_id=attempt.id,
                        trade_date=day,
                        ts_code=order.ts_code,
                        side=order.side,
                        quantity=order.quantity,
                        ref_open_price=money(decision.reference_price),
                        simulated_price=money(decision.fill_price),
                        gross_amount=decision.gross_amount,
                        cash_fee_total=decision.cash_fee_total,
                        total_cost=decision.total_cost,
                        cash_delta=decision.cash_delta,
                        fee_json=fee_json,
                    )
                )
                self.repo.add(
                    make_record(
                        PaperLedgerEntry,
                        owner,
                        str(fill.id),
                        now=now,
                        data={"fill_hash": fill.record_hash},
                        account_id=account.id,
                        day_run_id=execution_run.id,
                        fill_id=fill.id,
                        trade_date=day,
                        business_key=f"fill:{fill.id}",
                        entry_type="FILL",
                        cash_delta=fill.cash_delta,
                        quantity_delta=(fill.quantity if fill.side == "BUY" else -fill.quantity),
                        instrument=fill.ts_code,
                    )
                )
                if order.side == "BUY" and before_position is None:
                    new_codes.add(order.ts_code)
                working, contexts = prospective, prospective_contexts
                turnover += decision.gross_amount
                trading_cost += decision.total_cost
                self.fault_hook("after_fill")
            self.fault_hook("before_nav")
            snapshot = self.engine.mark_to_market(
                account=price_at_close(working, market),
                market=market,
                initial_cash=account.initial_cash,
                trading_cost=trading_cost,
            )
            snapshot = normalize_snapshot_for_persistence(
                snapshot, initial_cash=account.initial_cash
            )
            for position in snapshot.positions:
                self.repo.add(
                    make_record(
                        PaperPositionDaily,
                        owner,
                        f"{account.id}:{day}:{position.ts_code}",
                        now=now,
                        data={"context": contexts[position.ts_code]},
                        account_id=account.id,
                        day_run_id=close_run.id,
                        trade_date=day,
                        ts_code=position.ts_code,
                        quantity=position.quantity,
                        available_quantity=position.available_quantity,
                        avg_cost=position.avg_cost,
                        close_price=position.close_price,
                        market_value=position.market_value,
                        unrealized_pnl=position.unrealized_pnl,
                        realized_pnl=position.realized_pnl,
                        adj_factor=position.adj_factor,
                        valuation_source=position.valuation_source,
                        source_hash=source_hash,
                    )
                )
            benchmark_nav, benchmark_base = self._benchmark(account, day, facts)
            self.repo.add(
                make_record(
                    PaperNavDaily,
                    owner,
                    f"{account.id}:{day}",
                    now=now,
                    data={
                        "benchmark_base": benchmark_base,
                        "turnover": ratio(turnover / opening_assets),
                        "market_data_mode": config.policy.market_data_mode,
                    },
                    account_id=account.id,
                    day_run_id=close_run.id,
                    trade_date=day,
                    cash=snapshot.cash,
                    market_value=snapshot.market_value,
                    total_assets=snapshot.total_assets,
                    nav=snapshot.nav,
                    benchmark_nav=benchmark_nav,
                    benchmark_status="READY"
                    if benchmark_nav is not None
                    else "BENCHMARK_UNAVAILABLE",
                    trading_cost=snapshot.trading_cost,
                    position_count=len(snapshot.positions),
                    source_hash=source_hash,
                )
            )
            load_close(self.db, account, day, require_completed=False)
            self._expire_proposals(
                account, now, reader.settings.paper_config.decision.max_source_rows
            )
            result_hash = self._bundle(account, day)
            for row in checkpoints:
                row.status, row.result_hash = "SUCCESS", result_hash
            self.db.flush()
            self.fault_hook("before_commit")
            self.commit_guard(completed)
            self.db.commit()
            committed = True
            self.fault_hook("after_commit")
            return completed
        except Exception as exc:
            if not committed:
                self.db.rollback()
                if account is not None and isinstance(exc, PaperError) and exc.status_code != 404:
                    self._blocked(owner, account.id, day, exc.code)
            raise

    def _previous_date(self, day):
        from app.models.market_data import TradeCalendar

        calendar = self.db.get(TradeCalendar, day)
        if not calendar or not calendar.is_open or calendar.pretrade_date is None:
            raise PaperError("PAPER_CALENDAR_UNAVAILABLE")
        return calendar.pretrade_date

    def _verify_signals(self, owner, account, orders, reader, now):
        sources = {}
        for order in orders:
            plan = verify_record(order)
            approval = self.repo.owned(DecisionApprovalEvent, owner, order.approval_id)
            proposal = self.repo.owned(DecisionProposal, owner, order.proposal_id)
            event, proposal_data = verify_record(approval), verify_record(proposal)
            if approval.decision != "APPROVED" or proposal.state != "APPROVED":
                raise PaperError("PAPER_APPROVAL_INTEGRITY_ERROR")
            if (
                approval.event_at >= open_cutoff(order.scheduled_date)
                or next_open(self.db, order.signal_date) != order.scheduled_date
                or event["proposal_hash"] != proposal.record_hash
                or event["plan"] != verify_record(order)
            ):
                raise PaperError("PAPER_APPROVAL_INTEGRITY_ERROR")
            observation = self.repo.owned(DecisionObservation, owner, proposal.observation_id)
            frozen = verify_record(observation)
            if (
                order.signal_date != observation.signal_date
                or order.source_hash != frozen["source_hash"]
                or order.target_weight != approval.approved_target_weight
                or order.quantity != plan["quantity"]
                or order.side != plan["side"]
            ):
                raise PaperError("PAPER_APPROVAL_INTEGRITY_ERROR")
            if proposal_data["observation_hash"] != observation.record_hash:
                raise PaperError("PAPER_APPROVAL_INTEGRITY_ERROR")
            if observation.id not in sources:
                sources[observation.id] = reader.capture(
                    observation.signal_date, cutoff=now, include_codes=frozen["include_codes"]
                )
            current = sources[observation.id]
            if any(
                current[key] != frozen[key]
                for key in ("source_hash", "strategy_identity_hash", "candidate_snapshot_hash")
            ):
                raise PaperError("PAPER_SOURCE_DRIFT")

    def _benchmark(self, account, day, facts):
        benchmark = facts["benchmark"] or {}
        if day == account.first_trade_date:
            base = decimal_or_none(benchmark.get("pre_close"))
        else:
            first = self.db.scalar(
                select(PaperNavDaily).where(
                    PaperNavDaily.account_id == account.id,
                    PaperNavDaily.trade_date == account.first_trade_date,
                )
            )
            base = decimal_or_none(verify_record(first).get("benchmark_base"))
        close = decimal_or_none(benchmark.get("close"))
        if base is None or base <= 0 or close is None or close <= 0:
            return None, base
        return ratio(close / base), base

    def _bundle(self, account, day):
        hashes = []
        for model in (
            PaperOrderAttempt,
            PaperFill,
            PaperLedgerEntry,
            PaperPositionDaily,
            PaperNavDaily,
        ):
            rows = list(
                self.db.scalars(
                    select(model)
                    .where(
                        model.account_id == account.id,
                        model.owner_user_id == account.owner_user_id,
                        model.trade_date == day,
                    )
                    .order_by(model.id)
                )
            )
            for row in rows:
                verify_record(row)
            hashes.append([model.__tablename__, [row.record_hash for row in rows]])
        return content_hash(hashes)

    def _expire_proposals(self, account, now, max_rows):
        proposals = list(
            self.db.scalars(
                select(DecisionProposal)
                .where(
                    DecisionProposal.account_id == account.id,
                    DecisionProposal.owner_user_id == account.owner_user_id,
                    DecisionProposal.state.in_(("DRAFT", "PENDING_REVIEW")),
                    DecisionProposal.expires_at <= now,
                )
                .order_by(DecisionProposal.id)
                .limit(max_rows + 1)
                .with_for_update()
            )
        )
        if len(proposals) > max_rows:
            raise PaperError("PAPER_PROPOSAL_CAPACITY_EXCEEDED")
        for proposal in proposals:
            verify_record(proposal)
            proposal.state, proposal.version = "EXPIRED", proposal.version + 1
            key = f"proposal-expired:{proposal.id}"
            self.repo.add(
                make_record(
                    PaperAccountEvent,
                    account.owner_user_id,
                    key,
                    now=now,
                    data={
                        "kind": "DECISION_EXPIRED",
                        "proposal_id": str(proposal.id),
                        "proposal_hash": proposal.record_hash,
                        "expires_at": proposal.expires_at,
                    },
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=key,
                    request_hash=content_hash([str(proposal.id), proposal.expires_at]),
                )
            )

    def _mark_review(self, account_id, day):
        mark_day_review(self.db, account_id, day)

    def _blocked(self, owner, account_id, day, code):
        account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
        if code not in {
            "PAPER_DISABLED",
            "SOURCE_EOD_NOT_READY",
            "PAPER_ACCOUNT_NOT_ACTIVE",
            "PAPER_JOB_CANCELLED",
            "PAPER_JOB_LEASE_LOST",
            "PAPER_JOB_IDENTITY_INVALID",
        }:
            self._mark_review(account.id, day)
        request = "day-blocked:" + content_hash([str(account.id), day, code])
        request_lock(self.db, owner, "day-blocked", request)
        if self.repo.by_request(PaperAccountEvent, owner, request) is None:
            self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    request,
                    now=self.clock(),
                    data={"kind": "PAPER_DAILY_BLOCKED", "trade_date": day, "reason_code": code},
                    account_id=account.id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=request,
                    request_hash=content_hash([account.id, day, code]),
                )
            )
        self.db.commit()
