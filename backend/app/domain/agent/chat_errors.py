class AgentChatError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def chat_not_found() -> AgentChatError:
    return AgentChatError("CHAT_NOT_FOUND", "chat not found", status_code=404)


def chat_conflict(message: str = "another turn is already running") -> AgentChatError:
    return AgentChatError("CHAT_CONFLICT", message, status_code=409)


def llm_disabled() -> AgentChatError:
    return AgentChatError("LLM_DISABLED", "LLM chat is disabled", status_code=503)


def llm_not_configured() -> AgentChatError:
    return AgentChatError(
        "LLM_NOT_CONFIGURED", "LLM provider credential is not configured", status_code=503
    )


def budget_exceeded(message: str) -> AgentChatError:
    return AgentChatError("BUDGET_EXCEEDED", message, status_code=429)


def total_deadline_exceeded() -> AgentChatError:
    return AgentChatError(
        "AGENT_DEADLINE_EXCEEDED",
        "Agent chat exceeded its total deadline",
        status_code=504,
    )


def invalid_llm_tool_call(message: str) -> AgentChatError:
    return AgentChatError("LLM_INVALID_TOOL_CALL", message, status_code=502)
