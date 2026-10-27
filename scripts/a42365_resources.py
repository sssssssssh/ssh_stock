"""Concrete lifecycle driver: every resource action goes through one writer broker."""

from scripts.a42363_resources import ResourceDriver


class BrokerResourceDriver(ResourceDriver):
    def __init__(self, broker):
        super().__init__(
            None, broker.socket_directory, broker.secret_fd, None, broker.fixture_identity
        )
        self.broker = broker

    def create(self, item):
        return self.broker.dispatch(item, "create")

    def inspect(self, item):
        # Read original identity from the controller ledger at the lifecycle layer.
        # Broker's read-only inspect still requires the same kernel store lease.
        with self.broker.exclusive(item.scope):
            return (
                self.broker._inspect(item)
                if item.kind != "SOCKET_DIR"
                else self.socket_directory.inspect(item)
            )

    def start(self, item, original):
        return self.broker.dispatch(item, "start", original)

    def stop(self, item, original):
        return self.broker.dispatch(item, "stop", original)

    def remove(self, item, original):
        return self.broker.dispatch(item, "rm", original)
