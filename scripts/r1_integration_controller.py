"""Single development-only injectable controller. Public CLI always hard denies."""

from dataclasses import dataclass

from scripts.r1_integration_evidence import (
    deny_real,
    empty_measurements,
    source_identity,
    verify_business_sources,
)
from scripts.r1_real_root_protocol import FLAGS, require

STAGES = (
    "preflight",
    "owner_reservation",
    "frozen_input_readiness",
    "allowed_os_domain",
    "root_facade_contract",
    "typed_export",
    "comparison",
    "cleanup",
)


@dataclass(frozen=True)
class DevelopmentPermit:
    """Unprivileged in-process test marker, never a real experiment token."""

    purpose: str = "FAKE_INJECTION_ONLY"


def arm_plan(arm):
    require(arm in ("OFF1", "ON1"), "CONTROLLER_ARM")
    return {"arm": arm, "perf_diagnostics_enabled": arm == "ON1", "business_flags": dict(FLAGS)}


require_human_authorization = deny_real


def make_offline_context(request, sources, owner):
    from scripts.r1_real_root_adapter import OfflineContext

    return OfflineContext(request, sources, owner)


@dataclass
class OfflineIntegrationComponents:
    """Actual new adapters composed with explicitly FAKE external I/O.

    No production connector, authority, facade or real-Worker spawn is supplied.
    The frozen original bridge stays unconditional deny; real export evidence
    cannot enter this composite even if a caller changes a configuration bool.
    """

    pg_guard: object
    target: object
    connector: object
    seed: object
    owner: object
    offline_context: object
    facade: object
    fake_domain: object
    export_pair: object
    real_execution_allowed: bool = False

    def preflight(self):
        from scripts.r1_real_root_adapter import OfflineFacade

        require(
            self.real_execution_allowed is False
            and self.pg_guard.evidence_kind == "FAKE"
            and isinstance(self.facade, OfflineFacade),
            "CONTROLLER_FAKE_ONLY",
        )
        verify_business_sources()
        self.source = source_identity()
        self.receipt = self.pg_guard.inspect(self.connector, self.target)
        self.pg_guard.require_ready(self.receipt, self.target.owner_scope)
        self.binding = self.receipt.target_digest
        return {"fake_only": True, "source": self.source}

    def reserve_owner(self):
        require(hasattr(self, "receipt"), "CONTROLLER_PREFLIGHT_REQUIRED")
        return self.owner.reserve(self.binding)

    def execute_fake_root(self):
        from scripts.r1_real_root_adapter import execute_one_r1_root

        self.owner.confirm(self.binding)
        result = execute_one_r1_root(self.offline_context, self.facade, lambda _: None)
        require(
            result["status"] == "SUCCESS" and result["evidence_kind"] == "OFFLINE_SIMULATED",
            "CONTROLLER_FAKE_ROOT_FAILED",
        )
        return {
            "status": "OFFLINE_SIMULATED",
            "root_result": result,
            "real_worker_output_equal": False,
        }

    def freeze_inputs(self, left_reader, right_reader):
        manifest = self.seed.prepare_manifest()
        left = self.seed.plan_load("OFF1", "fake-loader-a", "fake-physical-a")
        right = self.seed.plan_load("ON1", "fake-loader-b", "fake-physical-b")
        a = self.seed.verify_loaded_snapshot(left, left_reader)
        b = self.seed.verify_loaded_snapshot(right, right_reader)
        result = self.seed.compare_loaded(a, b)
        require(result["fake_entity_bytes_equal"] is True, "CONTROLLER_INPUT_UNEQUAL")
        return manifest

    def export_and_compare(self, left_fixture, right_fixture, mappings):
        from scripts.r1_integration_pg_export import PgTypedExporter, compare_fake_exports

        packets = []
        for db, fixture in zip(self.export_pair(), (left_fixture, right_fixture), strict=True):

            def ack(binding, fixture=fixture):
                job = fixture["tables"]["job_run"][0]
                return {
                    "binding": binding,
                    "root_id": fixture["root_id"],
                    "worker": job["worker_id"],
                    "token": job["execution_token"],
                    "commit_ack": "KNOWN",
                    "lease": "CONFIRMED",
                    "connections_closed": True,
                    "cleanup_ack": "CONFIRMED",
                    "os_exit": "CONFIRMED",
                }

            packets.append(
                PgTypedExporter(self.pg_guard, self.target, evidence_kind="FAKE").export(
                    lambda _, db=db: db,
                    root_id=fixture["root_id"],
                    independent_evidence=ack,
                )
            )
        return compare_fake_exports(*packets, left_fixture, right_fixture, mappings)

    def run(self, *, left_reader, right_reader, left_fixture, right_fixture, mappings):
        def stage(name, **_):
            if name == "preflight":
                self.preflight()
            elif name == "owner_reservation":
                self.reserve_owner()
            elif name == "frozen_input_readiness":
                self.freeze_inputs(left_reader, right_reader)
            elif name == "allowed_os_domain":
                require(
                    self.fake_domain() == {"status": "OFFLINE_MODEL_COMPLETE"},
                    "CONTROLLER_DOMAIN_INCOMPLETE",
                )
            elif name == "root_facade_contract":
                self.execute_fake_root()
            elif name == "typed_export":
                self.comparison = self.export_and_compare(left_fixture, right_fixture, mappings)
            elif name == "comparison":
                return self.comparison
            elif name == "cleanup":
                # No OS/PG resource was created by this fake-I/O composite.
                # Retain the reservation and journal suspension, never free for ON.
                if hasattr(self, "binding") and self.owner.binding == self.binding:
                    self.owner.suspend(self.binding)
            return {"status": "FAKE_CONFIRMED"}

        return run_injected(stage, DevelopmentPermit())


def run_injected(step, permit, *, ci="PENDING"):
    require(
        type(permit) is DevelopmentPermit and permit.purpose == "FAKE_INJECTION_ONLY",
        "CONTROLLER_DEVELOPMENT_PERMIT_REQUIRED",
    )
    require(
        callable(step) and ci in ("SUCCESS", "PENDING", "UPSTREAM_CI_FAILURE"), "CONTROLLER_INPUT"
    )
    events, first_error, cleanup = [], None, False
    # This function has no path that imports or starts a business Worker. The
    # caller supplies FAKE contract stages; future real authority is not shipped.
    try:
        for name in STAGES[:-1]:
            result = step(name, mode="FAKE_INJECTION_ONLY", plan=arm_plan("OFF1"))
            require(type(result) is dict, "CONTROLLER_STAGE_INCOMPLETE")
            if name == "comparison":
                require(result.get("synthetic_equal") is True, "CONTROLLER_UNEQUAL")
            else:
                require(result == {"status": "FAKE_CONFIRMED"}, "CONTROLLER_STAGE_INCOMPLETE")
            events.append(name)
    except Exception:
        first_error = "CONTROLLER_STAGE_INCOMPLETE"
    finally:
        try:
            cleanup = step("cleanup", mode="FAKE_INJECTION_ONLY") == {"status": "FAKE_CONFIRMED"}
        except Exception:
            cleanup = False
        if not cleanup and first_error is None:
            first_error = "CONTROLLER_CLEANUP_UNCERTAIN"
    return {
        "status": "INCOMPLETE" if first_error else "INTEGRATION_CODE_READY_FOR_REVIEW",
        "first_error": first_error,
        "completed_stages": events,
        "cleanup_ack": cleanup,
        "source": source_identity(),
        "ci": ci,
        "experiment": "NO_GO",
        "R1": "PARTIAL",
        "AC05": "PARTIAL",
        "real_roots": 0,
        "measurements": empty_measurements(),
        "external_fencing": "NOT_PROVEN",
    }


def main(_argv=None):
    print("R1_REAL_EXECUTION_NOT_AUTHORIZED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
