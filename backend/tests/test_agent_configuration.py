from unittest.mock import Mock

import pytest

from signet.adapters import agent


@pytest.mark.parametrize("key", [None, "", "   ", "sk-..."])
def test_missing_key_does_not_crash_construction_or_call_openai(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", key)
    factory = Mock()
    monkeypatch.setattr(agent, "OpenAI", factory)
    adapter = agent.OpenAIAgentAdapter("source", "treasury", "issuer")
    assert adapter.is_configured is False
    with pytest.raises(agent.AgentConfigurationError, match="OPENAI_API_KEY"):
        adapter.propose("Send 1 XRP")
    factory.assert_not_called()


def test_injected_client_needs_no_environment_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = agent.OpenAIAgentAdapter("source", "treasury", "issuer", client=Mock())
    assert adapter.is_configured is True


def test_configured_client_is_created_only_when_a_proposal_is_requested(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-mocked-client")
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("offline test stops here")
    factory = Mock(return_value=client)
    monkeypatch.setattr(agent, "OpenAI", factory)
    adapter = agent.OpenAIAgentAdapter("source", "treasury", "issuer")
    assert adapter.is_configured is True
    factory.assert_not_called()
    with pytest.raises(RuntimeError, match="offline test stops here"):
        adapter.propose("Send 1 XRP")
    factory.assert_called_once_with(api_key="test-key-for-mocked-client")
