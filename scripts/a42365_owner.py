"""Independent, fixed Owner audit connections; target GUCs stay on target session."""

import os

from scripts.a42363_contract import require
from scripts.a42364_owner import verify_connection


class AuditConnectionFactory:
    def __init__(self, identity, authority, credentials, budget):
        self.identity, self.authority = identity, authority
        self.credentials, self.budget, self.index = credentials, budget, 0

    def open(self):
        self.authority.require("TARGET_SESSION_GUC")
        self.authority.require("BOOTSTRAP_AND_BUDGET")
        i = self.identity.verify(self.identity.scope)
        require(
            not any(
                k.startswith("PG") or k in ("DATABASE_URL", "TEST_DATABASE_URL") for k in os.environ
            ),
            "OWNER_AMBIENT_CONNECTION",
        )
        self.index += 1
        # Durable B slots prevent reset of this local index from granting a third connection.
        self.budget.reserve_audit(self.index, "AUTH")
        import psycopg

        require(psycopg.__version__ == "3.3.4", "DRIVER_VERSION")
        c = psycopg.connect(
            host=i.socket_host,
            port=5432,
            dbname=i.database,
            user=i.owner_role,
            password=self.credentials.read("OWNER", i),
            passfile="",
            sslmode="disable",
            connect_timeout=1,
            autocommit=True,
            options="-c statement_timeout=100 -c default_transaction_read_only=on "
            "-c search_path=pg_catalog",
        )
        try:
            verify_connection(c, i)
            # PinnedSessionSource performs exactly one fixed pg_stat_activity query
            # per fresh audit connection. Charge it before returning the connection.
            self.budget.reserve_audit(self.index, "SQL")
            return c
        except BaseException:
            c.close()
            raise
