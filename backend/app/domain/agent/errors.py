class AgentError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def invalid_argument(message: str) -> AgentError:
    return AgentError("INVALID_ARGUMENT", message, status_code=422)


def not_found(message: str) -> AgentError:
    return AgentError("NOT_FOUND", message, status_code=404)


def not_ready(message: str, *, code: str = "NOT_READY") -> AgentError:
    return AgentError(code, message, status_code=503)


def identity_mismatch(message: str) -> AgentError:
    return AgentError("SOURCE_IDENTITY_MISMATCH", message, status_code=409)
