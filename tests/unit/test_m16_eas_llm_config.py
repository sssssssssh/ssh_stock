import json

import httpx
import pytest
from app.core.agent_config import AgentConfig
from app.core.config import Settings, _apply_agent_llm_overrides
from app.domain.agent.chat_errors import AgentChatError
from app.services.agent.llm.contracts import ChatMessage
from app.services.agent.llm.factory import build_llm_provider
from app.services.agent.llm.openai_compatible import OpenAICompatibleProvider


@pytest.fixture
def eas_dotenv(tmp_path, monkeypatch):
    # Exercise this file's values, not the runner's or earlier tests' environment.
    for name in (
        "LLM_ENABLED",
        "LLM_ENDPOINT",
        "LLM_MODEL",
        "LLM_AUTH_SCHEME",
        "LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
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
    return env_file


def test_eas_dotenv_values_configure_effective_chat_identity(eas_dotenv) -> None:
    settings = Settings(_env_file=eas_dotenv)
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


@pytest.mark.parametrize("enabled", [True, False])
def test_eas_process_environment_overrides_dotenv(eas_dotenv, monkeypatch, enabled) -> None:
    for name, value in {
        "LLM_ENABLED": str(enabled).lower(),
        "LLM_ENDPOINT": "https://process.example.com/v1",
        "LLM_MODEL": "process-model",
        "LLM_AUTH_SCHEME": "bearer",
        "LLM_API_KEY": "process-example-token",
    }.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=eas_dotenv)
    settings.agent_config = _apply_agent_llm_overrides(AgentConfig(), settings)

    assert settings.llm_enabled is enabled
    assert settings.agent_config.llm_enabled is enabled
    assert settings.agent_config.mode == ("llm_chat" if enabled else "tools_only")
    assert str(settings.agent_config.llm.base_url) == "https://process.example.com/v1"
    assert settings.agent_config.llm.model == "process-model"
    assert settings.agent_config.llm.auth_scheme == "bearer"
    assert settings.llm_api_key.get_secret_value() == "process-example-token"
    assert "process-example-token" not in repr(settings)
    assert "old-example-token" not in repr(settings)
    if enabled:
        provider = build_llm_provider(settings)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._api_key == "process-example-token"
    else:
        with pytest.raises(AgentChatError) as caught:
            build_llm_provider(settings)
        assert caught.value.code == "LLM_DISABLED"


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
