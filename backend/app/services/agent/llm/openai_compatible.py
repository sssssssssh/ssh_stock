from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.agent_llm_config import AgentLLMConfig
from app.services.agent.llm.contracts import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    LLMTool,
    LLMUsage,
    ProviderError,
    ToolCall,
)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        config: AgentLLMConfig,
        api_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._api_key = api_key
        self._client = client

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[LLMTool],
        *,
        timeout: float,
        request_id: str,
    ) -> LLMResponse:
        payload = {
            "model": self.config.model,
            "messages": [_message_payload(message) for message in messages],
            "tools": [_tool_payload(tool) for tool in tools],
            "tool_choice": "auto",
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        }
        response = self._post(payload, timeout=timeout, request_id=request_id)
        return _parse_response(response)

    def _post(
        self, payload: dict[str, Any], *, timeout: float, request_id: str
    ) -> httpx.Response:
        endpoint = f"{str(self.config.base_url).rstrip('/')}/chat/completions"
        deadline = time.monotonic() + timeout
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        for attempt in range(self.config.max_provider_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError(
                    "LLM_TIMEOUT", "LLM provider request timed out", status_code=504
                )
            try:
                if self._client is not None:
                    response = self._client.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=remaining,
                    )
                else:
                    with httpx.Client() as client:
                        response = client.post(
                            endpoint,
                            headers=headers,
                            json=payload,
                            timeout=remaining,
                        )
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    "LLM_TIMEOUT", "LLM provider request timed out", status_code=504
                ) from exc
            except httpx.RequestError as exc:
                raise ProviderError(
                    "LLM_PROVIDER_UNAVAILABLE",
                    "LLM provider is unavailable",
                    status_code=503,
                ) from exc

            if response.status_code != 429 or attempt >= self.config.max_provider_retries:
                break

        if response.status_code in {401, 403}:
            raise ProviderError(
                "LLM_AUTHENTICATION_FAILED",
                "LLM provider authentication failed",
                status_code=503,
            )
        if response.status_code == 429:
            raise ProviderError(
                "LLM_RATE_LIMITED", "LLM provider rate limit exceeded", status_code=429
            )
        if response.status_code >= 500:
            raise ProviderError(
                "LLM_PROVIDER_UNAVAILABLE",
                "LLM provider is unavailable",
                status_code=503,
            )
        if response.status_code in {400, 422} and _is_tool_call_unsupported(response):
            raise ProviderError(
                "LLM_TOOL_CALL_UNSUPPORTED",
                "LLM provider does not support tool calling",
                status_code=502,
            )
        if response.status_code >= 400:
            raise ProviderError(
                "LLM_PROVIDER_REJECTED",
                "LLM provider rejected the request",
                status_code=502,
            )
        return response


def _message_payload(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role}
    if message.content is not None:
        payload["content"] = message.content
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            }
            for call in message.tool_calls
        ]
    return payload


def _is_tool_call_unsupported(response: httpx.Response) -> bool:
    """Recognize common OpenAI-compatible capability errors without exposing them."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return False
    code = str(error.get("code") or error.get("type") or "").lower()
    message = str(error.get("message") or "").lower()
    known_codes = {
        "function_calling_not_supported",
        "tool_calls_not_supported",
        "tool_calls_unsupported",
        "unsupported_tools",
    }
    return code in known_codes or (
        any(term in message for term in ("tool", "function call"))
        and any(term in message for term in ("not support", "unsupported"))
    )


def _tool_payload(tool: LLMTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_response(response: httpx.Response) -> LLMResponse:
    try:
        payload = response.json()
        choice = payload["choices"][0]
        message = choice["message"]
        raw_calls = message.get("tool_calls") or []
        content = message.get("content")
        if raw_calls and content:
            raise ValueError("provider returned mixed final text and tool calls")
        calls = [_parse_tool_call(item) for item in raw_calls]
        usage_raw = payload.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
        )
        return LLMResponse(
            final_text=content.strip() if isinstance(content, str) else None,
            tool_calls=calls,
            provider_request_id=response.headers.get("x-request-id") or payload.get("id"),
            usage=usage,
        )
    except (
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        raise ProviderError(
            "LLM_INVALID_RESPONSE",
            "LLM provider returned an invalid response",
            status_code=502,
        ) from exc


def _parse_tool_call(payload: Any) -> ToolCall:
    if not isinstance(payload, dict) or payload.get("type", "function") != "function":
        raise ValueError("unsupported tool call")
    function = payload.get("function")
    if not isinstance(function, dict):
        raise ValueError("missing function payload")
    raw_arguments = function.get("arguments")
    if not isinstance(raw_arguments, str):
        raise ValueError("tool arguments must be JSON text")
    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must decode to an object")
    return ToolCall(
        id=payload.get("id"),
        name=function.get("name"),
        arguments=arguments,
    )
