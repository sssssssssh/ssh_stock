"""Closed B budget RPC and pre-effect mediation. No executable is chosen by RPC."""

from typing import Literal

from pydantic import model_validator

from scripts.a4235_calibration_adapter_contract import Strict
from scripts.a42361_contract import checked
from scripts.a42363_contract import require, verify_receipt


class BudgetRequest(Strict):
    operation: Literal["NAMED", "FILESYSTEM", "AUDIT", "NATIVE"]
    name: str | None = None
    step: int | None = None
    index: int | None = None
    kind: Literal["AUTH", "SQL"] | None = None

    @model_validator(mode="after")
    def exact_fields(self):
        fields = {"NAMED": {"name"}, "FILESYSTEM": {"step"}, "AUDIT": {"index", "kind"},
                  "NATIVE": {"index"}}[self.operation]
        if self.model_fields_set != fields | {"operation"}:
            raise ValueError("BUDGET_REQUEST_FIELDS")
        if any(getattr(self, field) is None for field in fields):
            raise ValueError("BUDGET_REQUEST_FIELDS")
        return self


def reserve_request(budget, raw):
    q = checked(BudgetRequest, raw)
    if q.operation == "NAMED":
        return budget.reserve_named(q.name)
    if q.operation == "FILESYSTEM":
        return budget.reserve_filesystem(q.step)
    if q.operation == "AUDIT":
        return budget.reserve_audit(q.index, q.kind)
    return budget.native_exec(q.index)


class RemoteBudget:
    def __init__(self, client):
        require(client.domain == "consumer", "BUDGET_WRITER_DOMAIN")
        self.client = client

    def _reserve(self, body):
        checked(BudgetRequest, body)
        raw = self.client.call("budget", body)
        r = verify_receipt(raw, "consumer", self.client.scope)
        return r

    def reserve_named(self, name, now_ns=None, wall_ms=None):
        return self._reserve(dict(operation="NAMED", name=name))

    def reserve_filesystem(self, step):
        return self._reserve(dict(operation="FILESYSTEM", step=step))

    def reserve_audit(self, index, kind):
        return self._reserve(dict(operation="AUDIT", index=index, kind=kind))

    def native_exec(self, ordinal):
        return self._reserve(dict(operation="NATIVE", index=ordinal))


class PreEffectOperations:
    """Installer supplies fixed operations, never request code or argv.

    Native operations are unconditionally closed until an independent kernel
    execution mediator/census is installed. A DAG slot is not such a capability.
    """

    def __init__(self, identity, authority, budget, journal, operations):
        self.identity, self.authority, self.budget = identity, authority, budget
        self.journal, self.operations = journal, dict(operations)

    def perform(self, name):
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        require(name in self.operations and name in self.budget.operations,
                "UNACCOUNTED_BOOTSTRAP_OPERATION")
        op = self.budget.operations[name]
        require(op["commands"] == 0 and not name.startswith("IMAGE_"),
                "NATIVE_TRANSITIVE_CENSUS_UNPROVEN")
        scope = self.identity.scope
        from scripts.a42361_contract import sha

        key = "EFFECT_" + sha(name.encode())[:40]
        require(self.journal.maybe_read(scope, key + "_ATTEMPTED") is None,
                "EFFECT_ACK_UNKNOWN_NO_REPLAY")
        reserved = self.budget.reserve_named(name)
        self.journal.append(scope, key + "_ATTEMPTED", dict(
            operation=name, reservation_digest=reserved.digest, qualifies=False,
        ))
        result = self.operations[name]()
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        return self.journal.append(scope, key + "_COMMITTED", dict(
            operation=name, result=result, reservation_digest=reserved.digest, qualifies=False,
        ))
