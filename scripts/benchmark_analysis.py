import argparse
import time
from datetime import date

from app.core.db import SessionLocal
from app.services.factors import FactorService
from app.services.market import MarketService
from app.services.opportunity import OpportunityService
from app.services.sector import SectorService
from app.services.theme import ThemeFactorService
from app.services.trend import TrendService


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark analysis stages on a date range")
    parser.add_argument("--start", required=True, type=_date)
    parser.add_argument("--end", required=True, type=_date)
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must not be earlier than --start")
    with SessionLocal() as db:
        stages = (
            ("Factor", lambda: FactorService(db).recalc(args.start, args.end)),
            ("Market", lambda: MarketService(db).recalc(args.start, args.end)),
            ("Sector", lambda: SectorService(db).recalc(args.start, args.end)),
            ("Theme", lambda: ThemeFactorService(db).recalc(args.start, args.end)),
            ("Trend", lambda: TrendService(db).recalc(args.start, args.end)),
            ("Opportunity", lambda: OpportunityService(db).recalc(args.start, args.end)),
        )
        for name, operation in stages:
            started = time.perf_counter()
            operation()
            print(f"{name} seconds: {time.perf_counter() - started:.3f}")


if __name__ == "__main__":
    main()
