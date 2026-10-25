"""Same-session counter evidence, not inferred server steady state or cached structure."""

import hashlib
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash, Strict, digest
from scripts.a4235_prepared_probe import Session
from scripts.a4236_g1_harness_contract import Counter, Positive, checked, require
from scripts.a4236_g1_probe import request


class PreparedRow(Strict):
    identifier_sha256: Hash
    parameter_oids: tuple[Positive, ...]
    from_sql: Literal[False] = False
    generic_plans: Counter
    custom_plans: Counter


class Snapshot(Strict):
    session: Session
    driver_sql_sha256: Hash
    protocol_sql_sha256: Hash
    parameter_oids: tuple[Positive, ...]
    cache_key_sha256: Hash
    observed_ns: Positive
    driver_executions: Counter
    driver_prepare_sent: bool
    row: PreparedRow | None
    evicted: Literal[False] = False
    projection_executions: Counter
    projection_is_zero_overhead: Literal[False] = False
    target: Literal["G1_SYNTHETIC_ONLY"] = "G1_SYNTHETIC_ONLY"
    evidence_kind: Literal["MOCK_ONLY"] = "MOCK_ONLY"


def cache_key(session, driver_sha, oids):
    return digest(
        [
            session.connection_sha256,
            session.connection_generation,
            session.pool_checkout_generation,
            driver_sha,
            oids,
        ]
    )


def validate_snapshot(value, expected_session, template):
    value, expected_session = checked(Snapshot, value), checked(Session, expected_session)
    sql = request(template)
    require(
        template != "PROJECTION"
        and value.session == expected_session
        and value.driver_sql_sha256 == sql.driver_sql_sha256
        and value.protocol_sql_sha256 == sql.protocol_sql_sha256
        and value.parameter_oids == sql.parameter_oids
        and value.cache_key_sha256
        == cache_key(expected_session, value.driver_sql_sha256, value.parameter_oids),
        "A4236_PREPARED_CONTINUITY_LOST",
    )
    if value.row is not None:
        require(
            value.driver_prepare_sent
            and value.row.parameter_oids == value.parameter_oids
            and value.row.generic_plans + value.row.custom_plans <= value.driver_executions,
            "A4236_PREPARED_CONTINUITY_LOST",
        )
    return value


def compare(before, after, expected_session, template):
    before = validate_snapshot(before, expected_session, template)
    after = validate_snapshot(after, expected_session, template)
    require(
        after.observed_ns > before.observed_ns
        and after.driver_executions >= before.driver_executions
        and after.projection_executions >= before.projection_executions
        and (not before.driver_prepare_sent or after.driver_prepare_sent),
        "A4236_PREPARED_CONTINUITY_LOST",
    )
    if before.row is not None:
        require(
            after.row is not None and before.row.identifier_sha256 == after.row.identifier_sha256,
            "A4236_PREPARED_CONTINUITY_LOST",
        )
        a, b = before.row, after.row
        delta = after.driver_executions - before.driver_executions
        require(
            b.generic_plans >= a.generic_plans
            and b.custom_plans >= a.custom_plans
            and (b.generic_plans - a.generic_plans + b.custom_plans - a.custom_plans) <= delta,
            "A4236_PREPARED_CONTINUITY_LOST",
        )
        require(
            not (b.generic_plans > a.generic_plans and b.custom_plans > a.custom_plans)
            and not (a.generic_plans == 0 < b.generic_plans and a.custom_plans > 0)
            and not (a.custom_plans == 0 < b.custom_plans and a.generic_plans > 0),
            "A4236_PLAN_MODE_DRIFT",
        )
    return dict(
        evidence_kind="MOCK_ONLY",
        prepared_capability="DRIVER_MODEL_ONLY",
        server_same_session="MOCK_VISIBLE" if after.row is not None else "PARTIAL",
        cached_plan_structure="CACHED_PLAN_STRUCTURE_NOT_VERIFIED",
        c0_c1_status="NOT_PROVEN",
        prepared_stable=False,
        physical_status="NOT_RUN",
        snapshot_sha256=digest(after.model_dump()),
    )


def sanitize_projection(rows):
    """Whitelist projection shape. Hash names immediately, never persist original names."""
    require(type(rows) in (list, tuple) and len(rows) <= 8, "A4236_ROW_BUDGET_EXCEEDED")
    output = []
    try:
        for row in rows:
            require(
                type(row) is tuple
                and len(row) == 5
                and type(row[0]) is str
                and 0 < len(row[0]) <= 128,
                "A4236_PROJECTION_INVALID",
            )
            output.append(
                PreparedRow(
                    identifier_sha256=hashlib.sha256(row[0].encode()).hexdigest(),
                    parameter_oids=tuple(row[1]),
                    from_sql=row[2],
                    generic_plans=row[3],
                    custom_plans=row[4],
                )
            )
        require(
            len({r.identifier_sha256 for r in output}) == len(output), "A4236_PROJECTION_INVALID"
        )
        return tuple(output)
    except Exception:
        from scripts.a4236_g1_harness_contract import Fault

        raise Fault("A4236_PROJECTION_INVALID") from None
