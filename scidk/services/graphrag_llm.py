from __future__ import annotations
from typing import Optional, Any, Dict

class OllamaLLMAdapter:
    """
    Minimal Ollama adapter to satisfy neo4j-graphrag LLM expectations.
    Provides a .complete(prompt: str) -> str and optionally a .chat(messages) -> str.
    Lazy-imports ollama only when instantiated.
    """
    def __init__(self, model: str = "llama3:8b", host: Optional[str] = None):
        try:
            from ollama import Client as _Client  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Ollama client not available: {e}")
        self._model = model
        self._client = _Client(host=host) if host else _Client()

    def complete(self, prompt: str, **kwargs) -> str:
        res = self._client.generate(model=self._model, prompt=prompt, options=kwargs or None)
        return res.get("response") or ""

    def chat(self, messages: Any, **kwargs) -> str:
        # messages: list of {role, content}
        res = self._client.chat(model=self._model, messages=messages, options=kwargs or None)
        msg = (res.get("message") or {})
        return msg.get("content") or ""
