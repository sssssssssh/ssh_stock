from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from app.domain.agent.report_errors import AgentReportError
from app.domain.decision.contracts import DecisionAction, PaperError
from app.models.paper import DecisionObservation, DecisionProposal, PaperAccount
from app.repositories.paper import PaperRepository
from app.services.agent.report.application import AgentReportApplication
from app.services.decision.source import DecisionSourceReadiness
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


class DecisionApplication:
    def __init__(self, db, settings, *, clock=utc_now):
        self.db, self.settings, self.clock = db, settings, clock
        self.repo = PaperRepository(db)
        self.source = DecisionSourceReadiness(db, settings)

    def enabled(self):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)

    def observe(self, owner_id, body):
        self.enabled()
        try:
            request_lock(self.db, owner_id, "observe", body.request_id)
            digest = request_hash(owner_id, "observe", body)
            existing = replay(
                self.repo.by_request(DecisionObservation, owner_id, body.request_id), digest
            )
            if existing:
                self.db.commit()
                return existing
            now = self.clock()
            source = self.source.capture(
                body.signal_date, cutoff=now, include_codes=body.include_codes
            )
            row = make_record(
                DecisionObservation,
                owner_id,
                body.request_id,
                now=now,
                data=source,
                signal_date=body.signal_date,
                source_status="READY",
                asof_cutoff=now,
                ready_at=source["ready_at"],
                strategy_identity_hash=source["strategy_identity_hash"],
                request_id=body.request_id,
                request_hash=digest,
            )
            self.repo.add(row)
            verify_record(row)
            self.db.commit()
            return row
        except Exception:
            self.db.rollback()
            raise

    def propose(self, owner_id, body):
        self.enabled()
        try:
            request_lock(self.db, owner_id, "propose", body.request_id)
            digest = request_hash(owner_id, "propose", body)
            existing = replay(
                self.repo.by_request(DecisionProposal, owner_id, body.request_id), digest
            )
            if existing:
                self.db.commit()
                return existing
            account = self.repo.owned(PaperAccount, owner_id, body.account_id, lock=True)
            if account.mode != "PAPER" or account.state == "CLOSED":
                raise PaperError("PAPER_ACCOUNT_CLOSED")
            observation = self.repo.owned(DecisionObservation, owner_id, body.observation_id)
            frozen = verify_record(observation)
            now = self.clock()
            current = self.source.capture(
                observation.signal_date, cutoff=now, include_codes=frozen["include_codes"]
            )
            if any(
                current[key] != frozen[key]
                for key in ("source_hash", "strategy_identity_hash", "candidate_snapshot_hash")
            ):
                raise PaperError("DECISION_SOURCE_DRIFT")
            candidate = next(
                (row for row in frozen["candidates"] if row["ts_code"] == body.ts_code), None
            )
            if candidate is None:
                raise PaperError("DECISION_SECURITY_MISMATCH", status_code=422)
            expires = open_cutoff(next_open(self.db, observation.signal_date))
            if body.action == DecisionAction.WATCH:
                expires = max(expires, now + timedelta(days=1))
            elif expires <= now:
                raise PaperError("DECISION_APPROVAL_WINDOW_EXPIRED")
            revision = 1
            if body.supersedes_id:
                previous = self.repo.owned(DecisionProposal, owner_id, body.supersedes_id)
                verify_record(previous)
                if previous.account_id != account.id or previous.ts_code != body.ts_code:
                    raise PaperError("DECISION_REVISION_MISMATCH")
                revision = previous.revision + 1
            report_ref = None
            if body.source_report_id:
                try:
                    report = AgentReportApplication(self.db, self.settings).get_report(
                        user=SimpleNamespace(id=owner_id),
                        report_id=body.source_report_id,
                    )
                except AgentReportError as exc:
                    raise PaperError(
                        "PAPER_NOT_FOUND" if exc.status_code == 404 else exc.code,
                        status_code=exc.status_code,
                    ) from exc
                if report.snapshot_hash != body.source_report_hash:
                    raise PaperError("DECISION_REPORT_HASH_MISMATCH")
                if (
                    report.as_of_date is None
                    or report.as_of_date > observation.signal_date
                    or report.created_at > now
                ):
                    raise PaperError("DECISION_REPORT_DATE_UNAVAILABLE")
                report_ref = {
                    "report_id": report.report_id,
                    "snapshot_hash": report.snapshot_hash,
                    "report_version": report.report_version,
                    "snapshot_level": report.snapshot_level,
                    "research_date": report.as_of_date,
                    "execution_authorization": False,
                }
            row = make_record(
                DecisionProposal,
                owner_id,
                body.request_id,
                now=now,
                data={
                    "candidate": candidate,
                    "observation_hash": observation.record_hash,
                    "source_hash": frozen["source_hash"],
                    "note": body.note,
                    "source_report": report_ref,
                },
                account_id=account.id,
                observation_id=observation.id,
                supersedes_id=body.supersedes_id,
                ts_code=body.ts_code,
                action=body.action.value,
                target_weight=body.target_weight,
                stage=candidate["opportunity_stage"],
                score=Decimal(candidate["opportunity_score"]).quantize(
                    Decimal("0.00000001"),
                    rounding=ROUND_HALF_UP,
                ),
                revision=revision,
                state="PENDING_REVIEW",
                version=1,
                expires_at=expires,
                request_id=body.request_id,
                request_hash=digest,
            )
            self.repo.add(row)
            verify_record(row)
            self.db.commit()
            return row
        except Exception:
            self.db.rollback()
            raise
