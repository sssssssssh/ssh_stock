"""Refuse an M13.4 downgrade that would silently delete phase checkpoints."""

import argparse
import os

from sqlalchemy import create_engine, inspect, text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight the destructive downgrade below 0035_m13_4_backtest_runner"
    )
    parser.add_argument(
        "--allow-checkpoint-data-loss",
        action="store_true",
        help="explicitly acknowledge deletion of every persisted backtest checkpoint",
    )
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            if "portfolio_backtest_checkpoint" not in inspect(connection).get_table_names():
                print("M13.4 checkpoint table is absent; downgrade preflight is not applicable")
                return
            count = int(
                connection.scalar(
                    text("SELECT count(*) FROM portfolio_backtest_checkpoint")
                )
                or 0
            )
    finally:
        engine.dispose()
    if count and not args.allow_checkpoint_data_loss:
        raise SystemExit(
            "REFUSED: downgrade would delete "
            f"{count} portfolio_backtest_checkpoint row(s). Export/retain the audit "
            "history, obtain an explicit data-loss approval, then rerun this preflight "
            "with --allow-checkpoint-data-loss before invoking Alembic downgrade."
        )
    acknowledgement = "explicitly acknowledged" if count else "no checkpoint rows"
    print(f"M13.4 downgrade preflight passed: {acknowledgement}")


if __name__ == "__main__":
    main()
