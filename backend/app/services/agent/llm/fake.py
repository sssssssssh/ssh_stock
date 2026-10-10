from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from app.services.agent.llm.contracts import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    LLMTool,
)


class FakeLLMProvider(LLMProvider):
    """Deterministic scripted provider for unit, integration and CI tests."""

    def __init__(self, responses: Iterable[LLMResponse | Exception]) -> None:
        self._responses = deque(responses)
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[LLMTool],
        *,
        timeout: float,
        request_id: str,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": [item.model_copy(deep=True) for item in messages],
                "tools": [item.model_copy(deep=True) for item in tools],
                "timeout": timeout,
                "request_id": request_id,
            }
        )
        if not self._responses:
            raise RuntimeError("FakeLLMProvider response script is exhausted")
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response.model_copy(deep=True)
