"""Candidate accounting DAG. Allocation is not a measured cold-start result."""

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import require
from scripts.a42363_proposals import BootstrapProposal

ACTIVE = dict(sql=8, commands=12, window_ms=2000)
CANDIDATE = dict(sql=12, commands=32, window_ms=30000)


def protocol_versions():
    return dict(active=dict(ACTIVE), candidate=dict(CANDIDATE), approved=False)


def cost_plan(identity, strategy="FRESH_DYNAMIC"):
    require(strategy in ("FRESH_DYNAMIC", "SINGLE_USE_PREBUILT"), "COST_STRATEGY")
    source = BootstrapProposal.fresh(identity)
    original = {o.name: o for o in source.operations}
    # initdb itself invokes backend helpers. Reserve five descendants, never count
    # the image/entrypoint as zero. The pinned image's actual exec census is an L2 gate.
    extra = [("IMAGE_INITDB_CHILD_" + str(i), "IMAGE_INITDB_INTERNAL", 1) for i in range(1, 6)]
    extra += [("OWNER_FIXTURE_AUTH_CONNECT", "AUTH_READINESS", 1)]
    steps = []
    root = [n for n in original if n.startswith("ROOT_")]
    creation = [
        n
        for n in original
        if n.startswith("C_") and n not in ("C_RUNNING_INSPECT", "C_READINESS_INSPECT")
    ]
    image = [n for n in original if n.startswith("IMAGE_")]
    inspection = [n for n in original if n.startswith("O_BEFORE_")]
    sql = [o.name for o in source.operations if o.kind == "SQL"]
    tail = [n for n in original if n.startswith("O_AFTER_")]
    order = root + creation + image + ["C_RUNNING_INSPECT", "C_READINESS_INSPECT"] + inspection
    order += ["OWNER_AUTH_CONNECT"] + sql + ["PROBE_AUTH_CONNECT"] + tail
    require(set(order) == set(original) and len(order) == len(original), "COST_OMITTED")
    previous = None
    for name in order:
        op = original[name]
        steps.append(
            dict(
                name=name,
                after=[] if previous is None else [previous],
                kind=op.kind,
                template=op.template,
                template_sha256=sha(op.template.encode()),
                sql=op.sql_cost,
                commands=op.command_cost,
                allocated_ms=op.worst_case_ms,
                cost_phase="BUILDER" if strategy == "SINGLE_USE_PREBUILT" else "RUNTIME",
            )
        )
        previous = name
    for name, kind, count in extra:
        steps.append(
            dict(
                name=name,
                after=["IMAGE_INITDB"] if "CHILD" in name else ["OWNER_AUTH_CONNECT"],
                kind=kind,
                template=name,
                template_sha256=sha(name.encode()),
                sql=0,
                commands=count,
                allocated_ms=300,
                cost_phase="RUNTIME",
            )
        )
    # Filesystem syscalls are explicitly recorded; they do not spawn a free hidden shell.
    return dict(
        version="a42364.bootstrap-candidate.v3",
        strategy=strategy,
        identity_sha256=source.identity_sha256,
        operations=steps,
        filesystem_operations=(
            "mkdirat PGDATA single-use",
            "HBA atomic write/fsync/rename",
            "socket/secret UID/GID/mode verification",
        ),
        total=dict(
            sql=sum(o["sql"] for o in steps),
            commands=sum(o["commands"] for o in steps),
            allocated_ms=sum(o["allocated_ms"] for o in steps),
        ),
        baseline_declared=dict(sql=12, commands=26),
        limits=dict(CANDIDATE),
        active_limits=dict(ACTIVE),
        initdb_descendant_reserve=5,
        transitive_exec_census="NOT_RUN_REQUIRED_FOR_PINNED_IMAGE",
        prebuilt_consumption="SINGLE_USE_REQUIRED_NO_FREE_BUILDER_COST",
        measured=False,
        cold_start_p95=None,
        approved=False,
        qualifies=False,
    )


def plan_digest(identity, strategy="FRESH_DYNAMIC"):
    return sha(canonical(cost_plan(identity, strategy)))


class CandidateBudget:
    def __init__(self, authority, now_ns):
        authority.require("BOOTSTRAP_AND_BUDGET")
        self.authority, self.started = authority, now_ns
        self.sql, self.commands, self.stopped = 0, 0, False

    def reserve(self, kind, now_ns):
        if type(now_ns) is not int or not 0 <= now_ns - self.started < 30_000_000_000:
            self.stopped = True
        require(
            not self.stopped,
            "CANDIDATE_BOOTSTRAP_DEADLINE",
        )
        require(kind in ("SQL", "COMMAND"), "CANDIDATE_BUDGET_KIND")
        field, limit = ("sql", 12) if kind == "SQL" else ("commands", 32)
        value = getattr(self, field)
        if value >= limit:
            self.stopped = True
            require(False, "CANDIDATE_BOOTSTRAP_BUDGET")
        setattr(self, field, value + 1)


class PersistentBootstrapBudget:
    """B-owned preassigned slots: SQL/command attempts survive process restart/ACK loss.

    No counter reset in O/C processes. A duplicate committed-or-unknown reservation
    fails permanently. Fixed names make the total bounded without racing SELECT/count.
    The root provisioner still has to wire every actual helper/exec to this broker.
    """

    def __init__(self, identity, authority, journal, boot_identity):
        self.identity, self.authority, self.journal = identity, authority, journal
        self.boot_identity = boot_identity
        self.plan = cost_plan(identity)
        self.operations = {v["name"]: v for v in self.plan["operations"]}
        require(journal.domain == "consumer", "BUDGET_WRITER_DOMAIN")

    def start(self, now_ns, wall_ms):
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        scope = self.identity.scope
        require(
            self.journal.maybe_read(scope, "BOOTSTRAP_V3_STARTED") is None,
            "BOOTSTRAP_NO_SECOND_START",
        )
        return self.journal.append(
            scope,
            "BOOTSTRAP_V3_STARTED",
            dict(
                started_ns=now_ns,
                wall_ms=wall_ms,
                boot_identity=self.boot_identity,
                plan_sha256=sha(canonical(self.plan)),
                qualifies=False,
            ),
        )

    def reserve_named(self, name, now_ns, wall_ms=None):
        import time

        self.authority.require("BOOTSTRAP_AND_BUDGET")
        scope = self.identity.scope
        started = self.journal.read(scope, "BOOTSTRAP_V3_STARTED")
        wall_ms = int(time.time() * 1000) if wall_ms is None else wall_ms
        require(
            started.record["boot_identity"] == self.boot_identity
            and started.record["plan_sha256"] == sha(canonical(self.plan)),
            "BOOTSTRAP_BUDGET_BINDING",
        )
        require(
            0 <= now_ns - started.record["started_ns"] < 30_000_000_000
            and 0 <= wall_ms - started.record["wall_ms"] < 30000,
            "CANDIDATE_BOOTSTRAP_DEADLINE",
        )
        require(name in self.operations, "UNACCOUNTED_BOOTSTRAP_OPERATION")
        event = "BUDGET_V3_" + sha(name.encode())[:32]
        require(self.journal.maybe_read(scope, event) is None, "BUDGET_ACK_UNKNOWN_NO_RETRY")
        op = self.operations[name]
        return self.journal.append(
            scope,
            event,
            dict(
                operation=name,
                sql=op["sql"],
                commands=op["commands"],
                plan_sha256=sha(canonical(self.plan)),
                qualifies=False,
            ),
        )
