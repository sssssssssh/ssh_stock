import json

import httpx
import pytest
from app.core.agent_config import AgentConfig
from app.core.config import Settings, _apply_agent_llm_overrides
from app.domain.agent.chat_errors import AgentChatError
from app.services.agent.llm.contracts import ChatMessage
from app.services.agent.llm.factory import build_llm_provider
from app.services.agent.llm.openai_compatible import OpenAICompatibleProvider


def test_eas_dotenv_values_configure_effective_chat_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "old-example-token")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_ENABLED=true\n"
        "LLM_ENDPOINT=https://eas.example.com/api/predict/demo/v1\n"
        "LLM_MODEL=deepseek-v4\n"
        "LLM_AUTH_SCHEME=raw\n"
        "LLM_API_KEY=example-token\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    settings.agent_config = _apply_agent_llm_overrides(AgentConfig(), settings)

    assert settings.agent_config.mode == "llm_chat"
    assert settings.agent_config.llm_enabled is True
    assert settings.agent_config.llm.model == "deepseek-v4"
    assert str(settings.agent_config.llm.base_url).endswith("/api/predict/demo/v1")
    assert settings.agent_config.llm.auth_scheme == "raw"
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._api_key == "example-token"
    assert "example-token" not in repr(settings)


def test_eas_provider_posts_to_chat_endpoint_with_raw_token() -> None:
    settings = Settings(
        _env_file=None,
        llm_endpoint="https://eas.example.com/api/predict/demo/v1",
        llm_model="deepseek-v4",
        llm_auth_scheme="raw",
    )
    config = _apply_agent_llm_overrides(AgentConfig(), settings).llm
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = OpenAICompatibleProvider(config, "example-token", client=client).complete(
            [ChatMessage(role="user", content="question")],
            [],
            timeout=1,
            request_id="request-1",
        )

    assert result.final_text == "ok"
    assert str(requests[0].url) == ("https://eas.example.com/api/predict/demo/v1/chat/completions")
    assert requests[0].headers["authorization"] == "example-token"
    assert json.loads(requests[0].content)["model"] == "deepseek-v4"


def test_disabled_chat_does_not_require_llm_api_key(tmp_path) -> None:
    settings = Settings(_env_file=None, llm_enabled=False)
    settings.agent_config = _apply_agent_llm_overrides(AgentConfig(), settings)

    assert settings.agent_config.mode == "tools_only"
    with pytest.raises(AgentChatError) as caught:
        build_llm_provider(settings)
    assert caught.value.code == "LLM_DISABLED"


def test_invalid_llm_endpoint_fails_closed() -> None:
    settings = Settings(_env_file=None, llm_endpoint="not-a-url")
    with pytest.raises(ValueError, match="base_url"):
        _apply_agent_llm_overrides(AgentConfig(), settings)
