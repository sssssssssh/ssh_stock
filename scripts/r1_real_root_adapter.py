"""One R1 orchestration algorithm. Live binding remains unconditionally sealed."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from scripts.r1_real_root_protocol import (
    Refused,
    digest,
    exact,
    real_execution_bridge,
    require,
    validate_request,
)


class OfflineFacade:
    """Trusted test injection boundary, never accepted via JSON or CLI."""

    evidence_kind = "OFFLINE_FAKE_FACADE"


class BusinessFacade:
    """Auditable late binding to actual signatures; the bridge always refuses."""

    def create_recalculation_job(self, db, *, start, end, evaluate_signals, mode):
        real_execution_bridge()
        from app.services.recalculation import create_recalculation_job

        return create_recalculation_job(
            db, start=start, end=end, evaluate_signals=evaluate_signals, mode=mode
        )

    def claim_next_job(self, db, worker_id):
        real_execution_bridge()
        from app.services.job_worker import claim_next_job

        return claim_next_job(db, worker_id)

    def execute_claimed_job(self, db, job_id, *, expected_worker, expected_token):
        real_execution_bridge()
        from app.services.job_worker import execute_claimed_job

        return execute_claimed_job(
            db, job_id, expected_worker=expected_worker, expected_token=expected_token
        )


@dataclass
class OfflineContext:
    request: dict
    source_hashes: dict
    owner: object
    used: bool = False
    mode: str = "OFFLINE_ONLY"


def execute_one_r1_root(context, facade, recorder):
    """Exercise create/claim/execute once against an explicitly offline facade.

    Facade.freeze returns a context manager for a session-local immutable test
    configuration/source binding. Adapter never commits, cancels or repairs DB rows.
    """
    require(type(context) is OfflineContext and context.mode == "OFFLINE_ONLY", "R1_CONTEXT")
    require(
        isinstance(facade, OfflineFacade) and facade.evidence_kind == "OFFLINE_FAKE_FACADE",
        "R1_FACADE",
    )
    validate_request(context.request, context.source_hashes)
    require(not context.used, "R1_REPLAY")
    context.used = True  # Burn even an owner refusal; no automatic replay.
    frozen = deepcopy(context.request)
    binding = digest(frozen)
    require(context.owner is not None, "R1_OWNER_REQUIRED")
    try:
        require(context.owner.reserve(binding) == "OFFLINE_RESERVED", "R1_OWNER_UNKNOWN")
        require(context.owner.confirm(binding, "BEFORE_ROOT") == "OFFLINE_ACK", "R1_OWNER_UNKNOWN")
    except Exception:
        raise Refused("R1_OWNER_UNKNOWN") from None
    events = []
    result = {
        "evidence_kind": "OFFLINE_SIMULATED",
        "decision": "NO_GO",
        "root_executions": 0,
        "status": "INCOMPLETE",
        "first_error": None,
        "real_execution_authorized": False,
        "binding": binding,
    }

    def record(phase):
        events.append(phase)
        recorder(phase)  # Injected memory sink; no path/file API.

    try:
        with facade.freeze(frozen["flags"], frozen["source_hashes"]):
            with facade.session() as db:
                record("CREATE")
                job = facade.create_recalculation_job(
                    db,
                    start=date(2026, 2, 23),
                    end=date(2026, 2, 24),
                    evaluate_signals=False,
                    mode="manual",
                )
                require(type(job.id) is UUID and job.status == "QUEUED", "R1_NEW_ROOT")
                require(
                    getattr(job, "_queue_deduplicated", None) is False
                    and job.job_type == "recalculate"
                    and job.parent_job_id is None
                    and job.depends_on_job_id is None,
                    "R1_NEW_ROOT",
                )
                require(type(job.job_metadata) is dict, "R1_ROOT_REQUEST")
                for key, value in {
                    "start": "2026-02-23",
                    "end": "2026-02-24",
                    "evaluate_signals": False,
                    "mode": "manual",
                    "dirty_range_ids": [],
                }.items():
                    exact(job.job_metadata.get(key), value)
                root_id = job.id
                worker = "perf03-r1-synthetic"
                record("CLAIM")
                require(facade.claim_next_job(db, worker) == root_id, "R1_WRONG_ROOT")
                db.refresh(job)
                claim = db.info.get("data_claim")
                require(
                    type(job.execution_token) is UUID
                    and job.worker_id == worker
                    and claim == (root_id, worker, job.execution_token)
                    and job.status == "RUNNING"
                    and job.id == root_id,
                    "R1_WRONG_OWNER_TOKEN",
                )
                token = job.execution_token
                require(
                    context.owner.confirm(binding, "BEFORE_EXECUTE") == "OFFLINE_ACK",
                    "R1_OWNER_UNKNOWN",
                )
                exact(context.request, frozen)
                record("EXECUTE")
                result["root_executions"] = 1
                facade.execute_claimed_job(
                    db, root_id, expected_worker=worker, expected_token=token
                )
                db.expire_all()
                observed = facade.observe(db, root_id)
                require(
                    type(observed) is dict
                    and set(observed)
                    == {
                        "root_id",
                        "worker_id",
                        "execution_token",
                        "status",
                        "publication",
                        "commit_ack",
                        "heartbeat_stopped",
                        "publication_confirmed",
                    },
                    "R1_OBSERVATION",
                )
                require(
                    (observed["root_id"], observed["worker_id"], observed["execution_token"])
                    == (root_id, worker, token),
                    "R1_WRONG_OWNER_TOKEN",
                )
                require(observed["commit_ack"] == "KNOWN", "R1_ACK_UNKNOWN")
                require(observed["heartbeat_stopped"] is True, "R1_HEARTBEAT_REMAINS")
                require(observed["publication_confirmed"] is True, "R1_PUBLICATION_UNCONFIRMED")
                status = observed["status"]
                require(
                    (status, observed["publication"])
                    in {
                        ("SUCCESS", "PUBLISHED"),
                        ("FAILED", "ABORTED"),
                        ("CANCELLED", "ABORTED"),
                    },
                    "R1_TERMINAL_RELATION",
                )
                result.update(status=status, publication=observed["publication"])
                if status != "SUCCESS":
                    result["first_error"] = "R1_" + status
                record("OBSERVED")
    except Refused as error:
        result["first_error"] = (
            str(error)
            if str(error)
            in {
                "R1_NEW_ROOT",
                "R1_ROOT_REQUEST",
                "R1_FIELD_TYPE",
                "R1_FIELD_VALUE",
                "R1_FIELDS",
                "R1_WRONG_ROOT",
                "R1_WRONG_OWNER_TOKEN",
                "R1_OWNER_UNKNOWN",
                "R1_OBSERVATION",
                "R1_ACK_UNKNOWN",
                "R1_HEARTBEAT_REMAINS",
                "R1_PUBLICATION_UNCONFIRMED",
                "R1_TERMINAL_RELATION",
            }
            else "R1_BUSINESS_EXCEPTION"
        )
    except Exception:
        result["first_error"] = "R1_BUSINESS_EXCEPTION"
    result["events"] = events
    # A fake return never means a real root, persisted publication or OS exit.
    return result


def main(_argv=None):
    print("R1_REAL_EXECUTION_NOT_AUTHORIZED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
