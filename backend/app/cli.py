from datetime import date, datetime
from zoneinfo import ZoneInfo

import typer

from app.core.config import ROOT_DIR, get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.jobs.scheduler import run_scheduler
from app.providers.tushare_provider import TushareProvider
from app.services.factors import FactorService
from app.services.job_guard import (
    ActiveIngestionJobError,
    create_queued_ingestion_job,
)
from app.services.job_worker import run_worker
from app.services.market import MarketService
from app.services.provider_smoke import run_provider_smoke_test
from app.services.research import SignalEvaluationService
from app.services.sector import SectorService
from app.services.trend import TrendService

cli = typer.Typer(no_args_is_help=True)


def _parse_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{name} must use YYYY-MM-DD format") from exc


def _today() -> date:
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def _queue_cli_job(db, job_type, target_trade_date, metadata):
    try:
        return create_queued_ingestion_job(
            db,
            job_type,
            target_trade_date,
            step="queued from cli",
            metadata={"source": "cli", **metadata},
        )
    except ActiveIngestionJobError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc


def _mask_token(token: str | None) -> str | None:
    if not token:
        return None
    normalized = token.strip().strip("'\"")
    if len(normalized) <= 8:
        return "***"
    return f"{normalized[:4]}***{normalized[-4:]}"


@cli.command("check-config")
def check_config() -> None:
    settings = get_settings()
    token = settings.tushare_token
    normalized = token.strip().strip("'\"") if token else ""
    typer.echo(f"env_file={ROOT_DIR / '.env'}")
    typer.echo(f"database_url_configured={bool(settings.database_url)}")
    typer.echo(f"tushare_token_loaded={bool(normalized)}")
    typer.echo(f"tushare_token_length={len(normalized)}")
    typer.echo(f"tushare_token_masked={_mask_token(token)}")
    typer.echo(f"tushare_http_url={settings.tushare_http_url or ''}")
    typer.echo(f"tushare_min_interval_seconds={settings.tushare_min_interval_seconds}")
    typer.echo(f"app_timezone={settings.app_timezone}")


@cli.command("check-tushare")
def check_tushare() -> None:
    configure_logging()
    try:
        provider = TushareProvider()
        df = provider.get_trade_calendar(date(2026, 1, 1), date(2026, 1, 10))
    except Exception as exc:
        message = str(exc)
        if "token" in message.lower():
            typer.echo("tushare_ok=false error=TOKEN_INVALID_OR_NOT_ACCEPTED")
            typer.echo("Tushare server rejected the token read from .env.")
        else:
            typer.echo(f"tushare_ok=false error={type(exc).__name__}")
            typer.echo(message)
        raise typer.Exit(code=1) from exc

    typer.echo(f"tushare_ok=true rows={len(df.index)}")


@cli.command("provider-smoke-test")
def provider_smoke_test(
    trade_date: str | None = typer.Option(None, "--trade-date"),
) -> None:
    configure_logging()
    target = _parse_date(trade_date, "trade_date") if trade_date else _today()
    settings = get_settings()
    index_codes = settings.strategy.get("benchmark", {}).get(
        "market_indices", ["000300.SH"]
    )
    try:
        results = run_provider_smoke_test(
            TushareProvider(),
            target,
            index_codes=list(index_codes),
        )
    except Exception as exc:
        typer.echo(f"provider_smoke_ok=false error={type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc
    for result in results:
        if result.api_name == "theme_capability":
            typer.echo(f"theme_capability={result.status}")
            continue
        detail = f" detail={result.detail}" if result.detail else ""
        typer.echo(
            f"{result.api_name}: rows={result.rows} status={result.status}{detail}"
        )
    typer.echo("provider_smoke_ok=true")


@cli.command()
def daily(trade_date: str | None = typer.Option(None, "--trade-date")) -> None:
    configure_logging()
    target = _parse_date(trade_date, "trade_date") if trade_date else _today()
    with SessionLocal() as db:
        job = _queue_cli_job(db, "daily", target, {"trade_date": target.isoformat()})
    typer.echo(f"queued job_id={job.id}; run worker to execute")


@cli.command("sync-basic")
def sync_basic() -> None:
    configure_logging()
    with SessionLocal() as db:
        job = _queue_cli_job(db, "sync_basic", None, {"stage": "queued"})
    typer.echo(f"queued job_id={job.id}; run worker to execute")


@cli.command()
def backfill(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    configure_logging()
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    with SessionLocal() as db:
        job = _queue_cli_job(
            db,
            "backfill",
            end_date,
            {"start": start_date.isoformat(), "end": end_date.isoformat()},
        )
    typer.echo(f"queued job_id={job.id}; run worker to execute")


@cli.command("validate-data")
def validate_data(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    configure_logging()
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    with SessionLocal() as db:
        metadata = {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "stage": "queued",
            "progress_pct": 0,
        }
        job = _queue_cli_job(db, "validate_data", end_date, metadata)
    typer.echo(f"queued job_id={job.id}; run worker to execute")


@cli.command("recalc-factors")
def recalc_factors(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    configure_logging()
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    with SessionLocal() as db:
        rows = FactorService(db).recalc(start_date, end_date)
    typer.echo(f"stock_factor_daily rows={rows}")


@cli.command("recalc-market")
def recalc_market(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    configure_logging()
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    with SessionLocal() as db:
        rows = MarketService(db).recalc(start_date, end_date)
    typer.echo(f"market_daily rows={rows}")


@cli.command("recalc-sectors")
def recalc_sectors(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    configure_logging()
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    with SessionLocal() as db:
        rows = SectorService(db).recalc(start_date, end_date)
    typer.echo(f"sector_factor_daily rows={rows}")


@cli.command("recalc-states")
def recalc_states(
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    algo_version: str | None = typer.Option(None, "--algo-version"),
) -> None:
    configure_logging()
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    with SessionLocal() as db:
        rows = TrendService(db).recalc(start_date, end_date, algo_version=algo_version)
    typer.echo(f"stock_state_daily rows={rows['states']}")
    typer.echo(f"strategy_signal rows={rows['signals']}")


@cli.command("evaluate-signals")
def evaluate_signals(
    signal_type: str = typer.Option("RIGHT_SIDE_NEW", "--signal-type"),
    algo_version: str | None = typer.Option(None, "--algo-version"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    limit: int | None = typer.Option(None, "--limit"),
    eval_version: str = typer.Option("eval_v3", "--eval-version"),
    entry_basis: str = typer.Option("NEXT_OPEN", "--entry-basis"),
) -> None:
    configure_logging()
    start_date = _parse_date(start, "start") if start else None
    end_date = _parse_date(end, "end") if end else None
    with SessionLocal() as db:
        rows = SignalEvaluationService(db).evaluate(
            signal_type=signal_type,
            algo_version=algo_version,
            start=start_date,
            end=end_date,
            limit=limit,
            eval_version=eval_version,
            entry_basis=entry_basis,
        )
    typer.echo(f"strategy_signal rows={rows['signals']}")
    typer.echo(f"signal_forward_eval rows={rows['evaluated']}")


@cli.command()
def scheduler() -> None:
    configure_logging()
    run_scheduler()


@cli.command()
def worker() -> None:
    configure_logging()
    run_worker()


if __name__ == "__main__":
    cli()
