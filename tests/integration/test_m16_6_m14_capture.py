from datetime import date, timedelta

import sqlalchemy as sa
from app.core.config import get_settings
from app.domain.agent.contracts import PerformanceSummaryInput
from app.models.performance import PortfolioPerformanceDaily
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.contracts.capture import capture_research_contracts
from app.services.performance.period_application import PerformancePeriodApplicationService
from m14_4_support import seed_analytics_case
from sqlalchemy.orm import Session


def test_performance_tool_captures_selected_bundle_and_trade_dates_in_same_transaction():
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, expire_on_commit=False) as db:
                dates = tuple(date(2088, 1, 2) + timedelta(days=day) for day in range(21))
                case = seed_analytics_case(db, dates)
                period = PerformancePeriodApplicationService(db).calculate_now(
                    case.run_id,
                    performance_id=case.performance_id,
                    risk_id=case.risk_id,
                    trade_id=case.trade_id,
                ).report
                result = ResearchAgentAdapter(db).performance_summary(
                    PerformanceSummaryInput(run_id=case.run_id, report_id=case.performance_id)
                )
                assert str(result.identity["period_id"]) == str(period.id)
                drafts = capture_research_contracts(
                    db, result, tool_call_id="selected-call", max_trade_dates=100
                )
                assert len(drafts) == 1
                body = drafts[0].contract_json
                assert body["status"] == "COMPLETE"
                assert body["selected"]["performance_id"] == str(case.performance_id)
                assert body["comparison_contract"]["trade_dates"] == [
                    value.isoformat() for value in dates
                ]
                frozen = body["record"]["performance"]["annualized_return"]
                db.execute(
                    sa.update(PortfolioPerformanceDaily)
                    .where(PortfolioPerformanceDaily.performance_id == case.performance_id)
                    .values(nav=sa.literal(999))
                )
                assert body["record"]["performance"]["annualized_return"] == frozen
        finally:
            transaction.rollback()
            engine.dispose()
