class AgentReportError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def report_not_found() -> AgentReportError:
    return AgentReportError("REPORT_NOT_FOUND", "report not found", status_code=404)


def comparison_not_found() -> AgentReportError:
    return AgentReportError(
        "REPORT_COMPARISON_NOT_FOUND", "report comparison not found", status_code=404
    )


def idempotency_conflict() -> AgentReportError:
    return AgentReportError(
        "IDEMPOTENCY_CONFLICT",
        "request_id is already bound to different request content",
        status_code=409,
    )


def invalid_source(code: str, message: str) -> AgentReportError:
    return AgentReportError(code, message, status_code=422)
