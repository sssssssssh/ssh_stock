from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.chat.application import AgentChatApplication


def __getattr__(name):
    # Preserve the public convenience import without booting Chat for pure validation imports.
    if name == "AgentChatApplication":
        from app.services.agent.chat.application import AgentChatApplication
        return AgentChatApplication
    raise AttributeError(name)

__all__ = ["AgentChatApplication"]
