"""Stable, bounded titles for chat sessions."""


def title_from_message(message: str) -> str:
    """Use the opening user message without generating or exposing reply text."""
    title = " ".join(message.split())
    if not title:
        return "New chat"
    return title[:100].rstrip()
