import json
from decimal import Decimal

from sqlalchemy import func, select

from app.domain.decision.contracts import PaperError, canonical_json, content_hash
from app.domain.decision.performance import frozen_performance
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

    def summary(self, owner, account_id):
        account = PaperRepository(self.db).owned(PaperAccount, owner, account_id)
        verify_record(account)
        count = self.db.scalar(
            select(func.count())
            .select_from(PaperNavDaily)
            .where(PaperNavDaily.account_id == account.id, PaperNavDaily.owner_user_id == owner)
        )
        if count > self.settings.paper_config.decision.max_source_rows:
            raise PaperError("PAPER_HISTORY_CAPACITY_EXCEEDED")
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
                select(PaperDayRun).where(
                    PaperDayRun.account_id == account.id,
                    PaperDayRun.owner_user_id == owner,
                    PaperDayRun.phase == "DAY_COMPLETED",
                )
            )
        )
        completed = {head.trade_date for head in heads if head.status == "SUCCESS"}
        invalid = {row.trade_date.isoformat() for row in rows if row.trade_date not in completed}
        result = frozen_performance(
            projections,
            expected_dates=[d.isoformat() for d in expected],
            initial_cash=account.initial_cash,
            invalid_dates=invalid,
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
                    select(PaperPositionDaily).where(
                        PaperPositionDaily.account_id == account.id,
                        PaperPositionDaily.owner_user_id == owner,
                        PaperPositionDaily.trade_date == rows[-1].trade_date,
                    ).order_by(PaperPositionDaily.ts_code)
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
        result["decisions"] = dict(
            self.db.execute(
                select(DecisionProposal.state, func.count())
                .where(
                    DecisionProposal.account_id == account.id,
                    DecisionProposal.owner_user_id == owner,
                )
                .group_by(DecisionProposal.state)
            ).all()
        )
        orders = list(
            self.db.execute(
                select(PaperOrder, DecisionProposal.stage)
                .join(DecisionProposal, PaperOrder.proposal_id == DecisionProposal.id)
                .where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.owner_user_id == owner,
                    PaperOrder.status.in_(("FILLED", "SKIPPED", "EXPIRED")),
                )
            )
        )
        stages, blocked = {}, {}
        order_stages = {}
        for order, stage in orders:
            verify_record(order)
            counts = stages.setdefault(stage, {"orders": 0, "filled": 0})
            counts["orders"] += 1
            counts["filled"] += order.status == "FILLED"
            order_stages[order.id] = stage
            if order.reason_code:
                blocked[order.reason_code] = blocked.get(order.reason_code, 0) + 1
        reached, filled = len(orders), sum(order.status == "FILLED" for order, _ in orders)
        result["execution"] = {
            "reached_orders": reached,
            "filled_orders": filled,
            "hypothetical_fill_rate": ratio(Decimal(filled) / reached) if reached else None,
            "blocked_reasons": blocked,
            "stages": stages,
            "interpretation": "POST_EOD_SIMULATION_NON_CAUSAL",
        }
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
            "denominator": {"fills": len(fills)},
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
            "windows": observations,
            "source_hash": content_hash([review.record_hash for review in review_rows]),
        }
        return json.loads(canonical_json(result))
