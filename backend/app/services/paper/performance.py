import json
from decimal import Decimal

from sqlalchemy import Text, cast, func, select

from app.domain.decision.contracts import PaperError, canonical_json, content_hash
from app.domain.decision.performance import (
    decision_metrics,
    execution_metrics,
    frozen_performance,
    metric_range,
)
from app.models.market_data import TradeCalendar
from app.models.paper import (
    DecisionProposal,
    PaperAccount,
    PaperDayRun,
    PaperFill,
    PaperNavDaily,
    PaperOrder,
    PaperOutcomeReview,
    PaperPositionDaily,
)
from app.repositories.paper import PaperRepository
from app.services.paper.queries import projection
from app.services.paper.records import verify_record
from app.services.portfolio.ledger_precision import ratio


class PaperPerformance:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    def _preflight(self, owner, account):
        models = (
            PaperNavDaily,
            PaperDayRun,
            PaperFill,
            PaperPositionDaily,
            PaperOrder,
            DecisionProposal,
            PaperOutcomeReview,
        )
        counts, sizes = [], []
        for model in models:
            scope = (model.account_id == account.id, model.owner_user_id == owner)
            counts.append(select(func.count()).select_from(model).where(*scope).scalar_subquery())
            sizes.append(
                select(func.coalesce(func.sum(func.octet_length(cast(model.record_json, Text))), 0))
                .where(*scope)
                .scalar_subquery()
            )
        cap = self.settings.paper_config.decision.max_source_rows
        if sum(self.db.execute(select(*counts)).one()) > cap:
            raise PaperError("PAPER_HISTORY_CAPACITY_EXCEEDED")
        if (
            sum(self.db.execute(select(*sizes)).one())
            > self.settings.paper_config.max_history_bytes
        ):
            raise PaperError("PAPER_HISTORY_CAPACITY_EXCEEDED")
        last = (
            select(func.max(PaperNavDaily.trade_date))
            .where(PaperNavDaily.account_id == account.id, PaperNavDaily.owner_user_id == owner)
            .scalar_subquery()
        )
        calendar_count = self.db.scalar(
            select(func.count())
            .select_from(TradeCalendar)
            .where(
                TradeCalendar.is_open.is_(True),
                TradeCalendar.exchange.in_(("SSE", "SZSE")),
                TradeCalendar.cal_date >= account.first_trade_date,
                TradeCalendar.cal_date <= last,
            )
        )
        if calendar_count > cap:
            raise PaperError("PAPER_HISTORY_CAPACITY_EXCEEDED")

    def summary(self, owner, account_id):
        account = PaperRepository(self.db).owned(PaperAccount, owner, account_id)
        verify_record(account)
        self._preflight(owner, account)
        rows = list(
            self.db.scalars(
                select(PaperNavDaily)
                .where(PaperNavDaily.account_id == account.id, PaperNavDaily.owner_user_id == owner)
                .order_by(PaperNavDaily.trade_date)
            )
        )
        projections = [projection(row) for row in rows]
        expected = (
            list(
                self.db.scalars(
                    select(TradeCalendar.cal_date)
                    .where(
                        TradeCalendar.is_open.is_(True),
                        TradeCalendar.exchange.in_(("SSE", "SZSE")),
                        TradeCalendar.cal_date >= account.first_trade_date,
                        TradeCalendar.cal_date <= rows[-1].trade_date,
                    )
                    .order_by(TradeCalendar.cal_date)
                )
            )
            if rows
            else []
        )
        heads = list(
            self.db.scalars(
                select(PaperDayRun)
                .where(
                    PaperDayRun.account_id == account.id,
                    PaperDayRun.owner_user_id == owner,
                    PaperDayRun.phase == "DAY_COMPLETED",
                )
                .order_by(PaperDayRun.trade_date, PaperDayRun.id)
            )
        )
        for head in heads:
            verify_record(head)
        completed = {head.trade_date for head in heads if head.status == "SUCCESS"}
        invalid = {row.trade_date.isoformat() for row in rows if row.trade_date not in completed}
        result = frozen_performance(
            projections,
            expected_dates=[d.isoformat() for d in expected],
            initial_cash=account.initial_cash,
            invalid_dates=invalid,
            completion_heads=[{"record_hash": h.record_hash, "status": h.status} for h in heads],
        )
        fills = list(
            self.db.scalars(
                select(PaperFill)
                .where(PaperFill.account_id == account.id, PaperFill.owner_user_id == owner)
                .order_by(PaperFill.trade_date, PaperFill.id)
            )
        )
        realized = sum(
            (Decimal(verify_record(fill)["realized_delta"]) for fill in fills), Decimal("0")
        )
        positions = (
            list(
                self.db.scalars(
                    select(PaperPositionDaily)
                    .where(
                        PaperPositionDaily.account_id == account.id,
                        PaperPositionDaily.owner_user_id == owner,
                        PaperPositionDaily.trade_date == rows[-1].trade_date,
                    )
                    .order_by(PaperPositionDaily.ts_code)
                )
            )
            if rows
            else []
        )
        for position in positions:
            verify_record(position)
        result["realized_pnl"] = str(realized)
        result["unrealized_pnl"] = str(sum((p.unrealized_pnl for p in positions), Decimal("0")))
        result["financial_source_hash"] = content_hash(
            [row.record_hash for row in rows]
            + [fill.record_hash for fill in fills]
            + [p.record_hash for p in positions]
        )
        result["source_hash"] = content_hash(
            {
                "financial_source_hash": result["financial_source_hash"],
                "nav_evaluation_hash": result["source_hash"],
            }
        )
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
        result["decision_metrics"] = decision_metrics(
            [
                {
                    "record_hash": proposal.record_hash,
                    "state": proposal.state,
                    "version": proposal.version,
                    "action": proposal.action,
                    "signal_date": verify_record(proposal)["candidate"]["trade_date"],
                }
                for proposal in proposals
            ]
        )
        result["decisions"] = result["decision_metrics"]["counts"]
        orders = list(
            self.db.execute(
                select(PaperOrder, DecisionProposal.stage)
                .join(DecisionProposal, PaperOrder.proposal_id == DecisionProposal.id)
                .where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.owner_user_id == owner,
                )
                .order_by(PaperOrder.scheduled_date, PaperOrder.id)
            )
        )
        order_stages = {}
        order_facts = []
        for order, stage in orders:
            plan = verify_record(order)
            order_stages[order.id] = stage
            order_facts.append(
                {
                    "record_hash": order.record_hash,
                    "status": order.status,
                    "version": order.version,
                    "reason_code": order.reason_code,
                    "scheduled_date": order.scheduled_date.isoformat(),
                    "stage": stage,
                    "estimated_gross": plan.get("estimated_gross"),
                }
            )
        result["execution"] = execution_metrics(order_facts)
        attribution = {}
        for fill in fills:
            stage = order_stages.get(fill.order_id)
            if stage is None:
                raise PaperError("PAPER_LEDGER_INCONSISTENT")
            totals = attribution.setdefault(
                stage,
                {
                    "realized_pnl": Decimal("0"),
                    "unrealized_pnl": Decimal("0"),
                    "trading_cost": Decimal("0"),
                    "gross_amount": Decimal("0"),
                },
            )
            totals["realized_pnl"] += Decimal(verify_record(fill)["realized_delta"])
            totals["trading_cost"] += fill.total_cost
            totals["gross_amount"] += fill.gross_amount
        for position in positions:
            stage = verify_record(position)["context"]["opportunity_stage"]
            totals = attribution.setdefault(
                stage,
                {
                    "realized_pnl": Decimal("0"),
                    "unrealized_pnl": Decimal("0"),
                    "trading_cost": Decimal("0"),
                    "gross_amount": Decimal("0"),
                },
            )
            totals["unrealized_pnl"] += position.unrealized_pnl
        result["stage_attribution"] = {
            "eval_version": "m17-stage-attribution-v1",
            "allocation_policy": "REALIZED_BY_EXIT_PROPOSAL_UNREALIZED_BY_LAST_BUY_CONTEXT",
            "interpretation": "NON_CAUSAL",
            "date_range": result["date_range"],
            "source_hash": content_hash(
                [[str(f.order_id), f.record_hash, order_stages[f.order_id]] for f in fills]
                + [p.record_hash for p in positions]
            ),
            "denominator": {"fills": len(fills), "latest_positions": len(positions)},
            "sample_status": "LIMITED_OBSERVATIONAL_SAMPLE",
            "groups": {
                stage: {key: str(value) for key, value in totals.items()}
                for stage, totals in sorted(attribution.items())
            },
        }
        latest_reviews = (
            select(
                PaperOutcomeReview.proposal_id.label("proposal"),
                PaperOutcomeReview.window_days.label("window"),
                func.max(PaperOutcomeReview.asof_date).label("day"),
            )
            .where(
                PaperOutcomeReview.owner_user_id == owner,
                PaperOutcomeReview.account_id == account.id,
                PaperOutcomeReview.eval_version == "m17-outcome-mark-v1",
            )
            .group_by(PaperOutcomeReview.proposal_id, PaperOutcomeReview.window_days)
            .subquery()
        )
        review_rows = list(
            self.db.scalars(
                select(PaperOutcomeReview)
                .join(
                    latest_reviews,
                    (PaperOutcomeReview.proposal_id == latest_reviews.c.proposal)
                    & (PaperOutcomeReview.window_days == latest_reviews.c.window)
                    & (PaperOutcomeReview.asof_date == latest_reviews.c.day),
                )
                .where(
                    PaperOutcomeReview.account_id == account.id,
                    PaperOutcomeReview.owner_user_id == owner,
                    PaperOutcomeReview.eval_version == "m17-outcome-mark-v1",
                )
                .order_by(
                    PaperOutcomeReview.proposal_id,
                    PaperOutcomeReview.window_days,
                    PaperOutcomeReview.asof_date,
                )
            )
        )
        observations = {}
        for review in review_rows:
            data = verify_record(review)
            if not data["counterfactual"]:
                continue
            group = observations.setdefault(
                str(review.window_days),
                {"reviewed": 0, "valid_marks": 0, "positive_marks": 0, "hit_rate": None},
            )
            group["reviewed"] += 1
            if review.status == "READY" and data["forward_mark_return"] is not None:
                mark = Decimal(data["forward_mark_return"])
                if not mark.is_finite():
                    raise PaperError("PAPER_RECORD_INTEGRITY_ERROR")
                group["valid_marks"] += 1
                group["positive_marks"] += mark > 0
        for group in observations.values():
            if group["valid_marks"] and not invalid:
                group["hit_rate"] = ratio(Decimal(group["positive_marks"]) / group["valid_marks"])
        result["observation_metrics"] = {
            "eval_version": "m17-observation-hit-v1",
            "definition": "POSITIVE_FORWARD_MARK_OVER_VALID_COUNTERFACTUAL_MARKS",
            "deduplication": "LATEST_REVIEW_PER_PROPOSAL_WINDOW",
            "included_in_nav": False,
            "review_required": bool(invalid),
            "date_range": metric_range(r.asof_date.isoformat() for r in review_rows),
            "denominator": {
                "latest_reviews": len(review_rows),
                "counterfactual_reviews": sum(g["reviewed"] for g in observations.values()),
                "valid_marks": sum(g["valid_marks"] for g in observations.values()),
            },
            "windows": observations,
            "source_hash": content_hash(
                {
                    "reviews": [review.record_hash for review in review_rows],
                    "invalid_financial_dates": sorted(invalid),
                }
            ),
        }
        return json.loads(canonical_json(result))
