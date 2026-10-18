from datetime import date, datetime
from zoneinfo import ZoneInfo

import typer
from sqlalchemy.exc import DBAPIError

from app.core.config import ROOT_DIR, get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.jobs.research_job import queue_research_eval
from app.jobs.scheduler import run_scheduler
from app.providers.tushare_provider import TushareProvider
from app.services.auth.service import reset_admin_password as reset_admin_password_service
from app.services.job_guard import (
    ActiveIngestionJobError,
    ResearchQueueConflictError,
    create_queued_ingestion_job,
)
from app.services.job_worker import run_worker
from app.services.provider_smoke import run_provider_smoke_test

cli = typer.Typer(no_args_is_help=True)


@cli.command("data-job-diagnose")
def data_job_diagnose(job_id: str = typer.Option(..., "--job-id")) -> None:
    """Read incident evidence; never changes a Job or releases its slot."""
    import json
    from uuid import UUID

    from app.services.data_job_diagnostics import diagnose_data_job

    try:
        identity = UUID(job_id)
    except ValueError:
        raise typer.BadParameter("job-id must be UUID") from None
    try:
        with SessionLocal() as db:
            typer.echo(json.dumps(diagnose_data_job(db, identity), default=str, ensure_ascii=False))
    except DBAPIError:
        typer.echo("DATA_JOB_DIAGNOSTIC_DATABASE_UNAVAILABLE", err=True)
        raise typer.Exit(code=1) from None
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from None


@cli.command("retention-inventory")
def retention_inventory() -> None:
    import json

    from app.services.retention_lineage import reference_inventory

    try:
        with SessionLocal() as db:
            typer.echo(json.dumps(reference_inventory(db), default=str, ensure_ascii=False))
    except DBAPIError:
        typer.echo("RETENTION_DATABASE_ERROR", err=True)
        raise typer.Exit(code=1) from None


@cli.command("retention-check")
def retention_check(details: bool = typer.Option(False, "--details")) -> None:
    import json

    from app.services.retention import run_retention

    with SessionLocal() as db:
        result = run_retention(db, dry_run=True, include_diagnostics=details)
        typer.echo(json.dumps(result, default=str, ensure_ascii=False))
        if result["blocked"]:
            raise typer.Exit(code=1)


@cli.command("retention-run")
def retention_run(confirm: bool = typer.Option(False, "--confirm")) -> None:
    import json

    from app.core.retention_config import RetentionPolicy
    from app.services.retention import run_retention

    policy = RetentionPolicy.model_validate(get_settings().app_config.get("retention", {}))
    if not confirm or not policy.job_deletion_enabled:
        raise typer.BadParameter("requires --confirm and retention.job_deletion_enabled=true")
    with SessionLocal() as db:
        result = run_retention(db, policy=policy)
        typer.echo(json.dumps(result, default=str, ensure_ascii=False))
        if result["blocked"]:
            raise typer.Exit(code=1)


@cli.command("retention-indexes")
def retention_indexes(
    apply: bool = typer.Option(False, "--apply"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    import json

    from sqlalchemy import create_engine

    from app.services.retention_indexes import prepare_retention_indexes
    from app.services.retention_lineage import RetentionBlocked

    if apply and not confirm:
        raise typer.BadParameter("online index DDL requires --apply --confirm")
    engine = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            # Make the safety contract explicit to the index helper as well as the engine.
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            typer.echo(json.dumps(prepare_retention_indexes(connection, apply=apply)))
    except (DBAPIError, RetentionBlocked) as exc:
        code = str(exc) if isinstance(exc, RetentionBlocked) else "RETENTION_INDEX_DATABASE_ERROR"
        typer.echo(code, err=True)
        raise typer.Exit(code=1) from None
    finally:
        engine.dispose()


@cli.command("reset-admin-password")
def reset_admin_password() -> None:
    new_password = typer.prompt(
        "New password",
        hide_input=True,
        confirmation_prompt=True,
    )
    with SessionLocal() as db:
        try:
            reset_admin_password_service(db, get_settings().bootstrap_admin_username, new_password)
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
    typer.echo("admin password reset; all sessions revoked")


@cli.command("research-eval")
def research_eval(
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    opportunity_only: bool = typer.Option(False, "--opportunity-only"),
    theme_only: bool = typer.Option(False, "--theme-only"),
    transition_only: bool = typer.Option(False, "--transition-only"),
) -> None:
    try:
        with SessionLocal() as db:
            job = queue_research_eval(
                db,
                _parse_date(start, "start"),
                _parse_date(end, "end"),
                mode="cli",
                opportunity_only=opportunity_only,
                theme_only=theme_only,
                transition_only=transition_only,
            )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ResearchQueueConflictError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"research_eval queued job_id={job.id}; run worker to execute")


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
    index_codes = settings.strategy.get("benchmark", {}).get("market_indices", ["000300.SH"])
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
        typer.echo(f"{result.api_name}: rows={result.rows} status={result.status}{detail}")
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
    """Disabled unsafe single-table write; use explicit full recalculate or web UI."""
    _reject_direct_derived_write()


@cli.command("recalc-market")
def recalc_market(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    """Disabled unsafe single-table write; not silently mapped to full recalculate."""
    _reject_direct_derived_write()


@cli.command("recalc-sectors")
def recalc_sectors(start: str = typer.Option(...), end: str = typer.Option(...)) -> None:
    """Disabled unsafe single-table write; not silently mapped to full recalculate."""
    _reject_direct_derived_write()


@cli.command("recalc-states")
def recalc_states(
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    algo_version: str | None = typer.Option(None, "--algo-version"),
) -> None:
    """Disabled unsafe single-table write; algo-version is not silently discarded."""
    _reject_direct_derived_write()


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
    """Disabled direct evaluation: no equivalent queued signal-type/limit workflow."""
    _reject_direct_derived_write(evaluation=True)


def _reject_direct_derived_write(*, evaluation: bool = False) -> None:
    typer.echo("UNSAFE_DIRECT_DERIVED_WRITE_DISABLED: direct public writes are disabled.")
    typer.echo("Use the web 数据 page or explicitly select 'recalculate --start ... --end ...'.")
    typer.echo("Full recalculation is broader than this command; no request has been queued.")
    if evaluation:
        typer.echo(
            "No equivalent queued signal_type/limit/eval_version/entry_basis workflow; "
            "these options cannot be silently mapped to full recalculation."
        )
    raise typer.Exit(code=1)


@cli.command("recalculate")
def recalculate(
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    evaluate_signals: bool = typer.Option(True, "--evaluate-signals/--no-evaluate-signals"),
) -> None:
    """Enqueue FULL pipeline, not single-table recalc; Worker validates and atomically publishes."""
    start_date, end_date = _parse_date(start, "start"), _parse_date(end, "end")
    if start_date > end_date:
        raise typer.BadParameter("start must be <= end")
    with SessionLocal() as db:
        job = _queue_cli_job(
            db,
            "recalculate",
            end_date,
            {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "evaluate_signals": evaluate_signals,
                "mode": "manual",
            },
        )
    typer.echo(f"FULL recalculation queued job_id={job.id}; run worker to execute")


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
