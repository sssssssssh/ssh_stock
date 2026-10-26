"""Single, closed fixture target derived from committed Scope and installed UID policy."""

from typing import Literal

from scripts.a4235_calibration_adapter_contract import Strict
from scripts.a42361_contract import Positive, checked
from scripts.a42362_contract import Scope, resources
from scripts.a42363_contract import require, scope_hash


class Installation(Strict):
    worker_uid: Positive
    socket_gid: Positive
    pg_uid: Literal[999] = 999
    pg_gid: Literal[999] = 999
    socket_parent: Literal["/run/space-g1"] = "/run/space-g1"
    container_socket: Literal["/run/postgresql"] = "/run/postgresql"
    version: Literal["a42363.fixture.v1"] = "a42363.fixture.v1"


class FixtureIdentity(Strict):
    scope: Scope
    installation: Installation
    scope_sha256: str
    database: str
    owner_role: Literal["postgres"] = "postgres"
    probe_role: str
    socket_name: str
    socket_host: str
    container_name: str
    volume_name: str
    secret_name: str
    worker_uid: Positive
    controller_uid: Positive
    epoch: str
    image_digest: str
    namespace_sha256: str

    @classmethod
    def derive(cls, scope, installation):
        s, p = checked(Scope, scope), checked(Installation, installation)
        require(p.worker_uid != s.controller_uid, "FIXTURE_UID_PARTITION")
        rs = resources(s)
        suffix = s.binding.fixture_uuid.replace("-", "")
        return cls(
            scope=s,
            installation=p,
            scope_sha256=scope_hash(s),
            database="a42361_" + suffix,
            probe_role="a42363_probe_" + suffix,
            socket_name=rs[0].name,
            socket_host=p.socket_parent + "/" + rs[0].name,
            container_name=rs[3].name,
            volume_name=rs[1].name,
            secret_name=rs[2].name,
            worker_uid=p.worker_uid,
            controller_uid=s.controller_uid,
            epoch=s.epoch,
            image_digest=s.image_digest,
            namespace_sha256=s.namespace_sha256,
        )

    def verify(self, scope):
        require(self == self.derive(scope, self.installation), "FIXTURE_IDENTITY")
        return self

    def target(self):
        self.verify(self.scope)
        return dict(host=self.socket_host, database=self.database, user=self.probe_role, port=5432)

    def verify_credentials(self, credentials):
        self.verify(self.scope)
        require(
            type(credentials) is dict
            and set(credentials) == {"host", "database", "user", "password"}
            and all(credentials[k] == v for k, v in self.target().items() if k != "port")
            and type(credentials["password"]) is str
            and 32 <= len(credentials["password"]) <= 128,
            "FIXTURE_CREDENTIAL_TARGET",
        )
        return credentials
