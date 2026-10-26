"""Closed request schemas shared by installed receiver and client before transport."""

from dataclasses import dataclass

from scripts.a42361_contract import checked
from scripts.a42363_contract import Fault, lookup, require


@dataclass(frozen=True)
class MethodContract:
    domain: str
    method: str
    level: str = "NONQUALIFYING"

    def validate(self, body):
        from scripts.a42361_one_shot_store import ConsumeRequest, JournalRequest, ReceiptLookup
        from scripts.a42362_approval_registry_service import (
            ApprovalLookup,
            ImportRequest,
            KeyLookup,
        )
        from scripts.a42362_approval_registry_service import ReceiptLookup as ExternalReceipt
        from scripts.a42362_contract import LedgerRequest

        try:
            require(type(body) is dict, "RPC_BODY_SCHEMA")
            key = self.domain, self.method
            if self.method in ("import", "revoke"):
                checked(ImportRequest, body)
            elif key == ("registry", "key-status"):
                checked(KeyLookup, body)
            elif key == ("approval", "approval"):
                checked(ApprovalLookup, body)
            elif self.domain == "registry" and self.method == "receipt":
                checked(ExternalReceipt, body)
            elif self.domain == "approval" and self.method == "receipt" and set(body) != {"scope"}:
                checked(ExternalReceipt, body)
            elif self.domain == "consumer" and self.method in (
                "consume",
                "receipt",
                "journal",
                "resource-append",
            ):
                checked(
                    {
                        "consume": ConsumeRequest,
                        "receipt": ReceiptLookup,
                        "journal": JournalRequest,
                        "resource-append": LedgerRequest,
                    }[self.method],
                    body,
                )
            elif key == ("pg_owner", "receipt") and set(body) == {"purpose", "instance_sha256"}:
                require(
                    body["purpose"] == "CONTROL_PLANE_ISOLATION"
                    and type(body["instance_sha256"]) is str
                    and len(body["instance_sha256"]) == 64,
                    "RPC_BODY_SCHEMA",
                )
            else:
                lookup(body)
        except Exception:
            raise Fault("A42363_RPC_BODY_SCHEMA") from None
        return body


def request_contract(domain, method):
    from scripts.a42363_services import METHODS

    require(domain in METHODS and method in METHODS[domain], "RPC_METHOD")
    return MethodContract(domain, method)


class DomainClient:
    """Admin-installed transport only; a request cannot select a domain/peer endpoint."""

    def __init__(self, domain, transport):
        from scripts.a42363_services import METHODS

        require(domain in METHODS and transport is not None, "CLIENT_INSTALLATION")
        self.domain, self.transport = domain, transport

    def call(self, method, body):
        request_contract(self.domain, method).validate(body)
        return self.transport.call(method, body)
