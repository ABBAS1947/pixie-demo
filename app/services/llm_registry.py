"""LLM model registry — central place to configure which model handles which task.

Usage::

    from app.services.llm_registry import get_provider

    provider = get_provider("chat")          # main conversation
    provider = get_provider("extraction")    # structured extraction
    provider = get_provider("summarization") # summarization
    provider = get_provider("classification")# cheap classification

Adding a new provider or task is a one-line change here.
"""
from app.core.config import settings
from app.services.llm_provider import LLMProvider
from app.services.providers.deepseek_provider import DeepSeekProvider

# ── Task → provider mapping ───────────────────────────────────────────
# Each task gets its own provider instance with the right model.
# Models are configurable via the Settings object (env / .env file).

_MODELS: dict[str, LLMProvider] = {
    # Each task uses its own model, routed via settings so it can be changed
    # per task in .env (PIXIE_CHAT_MODEL, PIXIE_EXTRACTION_MODEL, ...) without
    # touching code. Defaults are the validated fast+clean model on this plan.
    "chat": DeepSeekProvider(model=settings.pixie_chat_model),
    "extraction": DeepSeekProvider(model=settings.pixie_extraction_model),
    "summarization": DeepSeekProvider(model=settings.pixie_summarization_model),
    "classification": DeepSeekProvider(model=settings.pixie_classification_model),
}


def get_provider(task: str = "chat") -> LLMProvider:
    """Return the LLM provider configured for *task*.

    Falls back to the ``"chat"`` provider for unknown task names.
    """
    return _MODELS.get(task, _MODELS["chat"])
