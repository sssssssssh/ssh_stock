import math
import time
from copy import deepcopy
from types import SimpleNamespace

import sqlalchemy as sa
from app.core.db import SessionLocal
from app.domain.agent.report import CreateReportComparison, CreateResearchReport
from app.models.agent_archive import AgentTurnArchiveManifest
from app.models.agent_report import AgentResearchReport
from app.services.agent.report.application import AgentReportApplication
from test_m16_4_research_reports import _cleanup, _source, _user
from test_m16_5_archive_migration import cleanup_archives
from test_m16_5_chat_archive import FixtureChat, archive_settings, provider


def test_0050_0051_upgrade_preserves_real_legacy_report_and_comparison_ids_json_hashes(
    archive_migration_database,
):
    owned = archive_migration_database
    settings = archive_settings()
    with owned.factory() as db:
        owner = _user(db, "upgrade-legacy")
        owner_id = owner.id
        try:
            service = AgentReportApplication(db, settings)
            reports = []
            for index in range(2):
                chat, message = _source(db, owner, value=str(index + 1))
                reports.append(
                    service.create_report(
                        user=owner,
                        body=CreateResearchReport(
                            source_chat_id=chat,
                            source_message_id=message,
                            report_type="strategy_review",
                            request_id=f"old-{index}",
                        ),
                    )
                )
            comparison = service.create_comparison(
                user=owner,
                body=CreateReportComparison(
                    left_report_id=reports[0].report_id,
                    right_report_id=reports[1].report_id,
                    request_id="legacy-compare",
                ),
            )
            frozen = deepcopy([item.snapshot.model_dump(mode="json") for item in reports])
            comparison_result = deepcopy(comparison.result)
            db.rollback()
            owned.migrate('downgrade', '0050_m16_4_reports')
            owned.migrate('upgrade', 'head')
            owned.migrate('upgrade', 'head')
            for report, expected in zip(reports, frozen, strict=True):
                view = service.get_report(
                    user=SimpleNamespace(id=owner_id), report_id=report.report_id
                )
                assert view.snapshot.model_dump(mode="json") == expected
                assert view.snapshot_hash == report.snapshot_hash
                assert view.report_version == "m16.4-v1"
            view = service.get_comparison(
                user=SimpleNamespace(id=owner_id), comparison_id=comparison.comparison_id
            )
            assert (
                view.result == comparison_result
                and view.comparison_hash == comparison.comparison_hash
            )
            assert db.scalar(sa.select(sa.func.count()).select_from(AgentTurnArchiveManifest)) == 0
            assert (
                db.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentResearchReport)
                    .where(AgentResearchReport.owner_user_id == owner_id)
                )
                == 2
            )
        finally:
            db.rollback()
            _cleanup(owner_id, session_factory=owned.factory)


def test_archive_serialization_and_atomic_write_latency_is_measured_not_assumed(monkeypatch):
    from app.services.agent.chat import application as chat_module

    serialization, writes = [], []
    assemble = chat_module.assemble_archive

    def measured_assemble(**kwargs):
        start = time.perf_counter()
        result = assemble(**kwargs)
        serialization.append((time.perf_counter() - start) * 1000)
        return result

    class MeasuredChat(FixtureChat):
        def _complete_turn(self, **kwargs):
            start = time.perf_counter()
            result = super()._complete_turn(**kwargs)
            writes.append((time.perf_counter() - start) * 1000)
            return result

    monkeypatch.setattr(chat_module, "assemble_archive", measured_assemble)
    with SessionLocal() as db:
        owner = _user(db, "perf")
        owner_id = owner.id
        try:
            settings = archive_settings()
            chat = MeasuredChat(db, settings).create_chat(user=owner, title="Synthetic performance")
            for index in range(22):
                MeasuredChat(db, settings, provider=provider()).send_message(
                    user=owner, chat_id=chat.chat_id, content="核验", request_id=f"perf-{index}"
                )
            serialization, writes = serialization[2:], writes[2:]

            def p95(values):
                return round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 3)

            print(
                {
                    "sample": "2 tools / 3 evidence / 3 facts",
                    "warmup": 2,
                    "samples": len(writes),
                    "serialization_p95_ms": p95(serialization),
                    "atomic_write_commit_p95_ms": p95(writes),
                    "combined_p95_ms": p95(
                        [a + b for a, b in zip(serialization, writes, strict=True)]
                    ),
                    "environment": "Python 3.12 Docker / PostgreSQL 17 isolated test database",
                }
            )
            assert len(writes) == 20 and all(value > 0 for value in writes)
        finally:
            cleanup_archives(owner_id)
