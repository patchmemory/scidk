"""
LLM Provider Abstraction for SciDK Chat.

Supports multiple backends: Ollama (local), Anthropic Claude, OpenAI.
All providers implement streaming for responsive UI.

Based on spec: dev/idea-import/chat-vision/ollama-scidk-integration.md
"""
from abc import ABC, abstractmethod
from typing import Generator, Dict, Any, Optional
import requests
import json


class LLMProvider(ABC):
    """Base class for all LLM providers.

    Schema grounding is built into the interface from day one.
    Providers receive schema_context and integrate it into their system prompts.
    """

    @abstractmethod
    def complete(self, user_message: str, system_prompt: Optional[str] = None,
                 schema_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Blocking completion - returns full response.

        Args:
            user_message: User query
            system_prompt: Base system prompt (optional)
            schema_context: Neo4j schema for grounding (optional, prevents hallucination)

        Returns:
            Complete response text
        """
        pass

    @abstractmethod
    def stream(self, user_message: str, system_prompt: Optional[str] = None,
               schema_context: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        """
        Streaming completion - yields tokens as they arrive.

        Critical for UX: At 13 tok/sec, streaming makes 15s responses feel instant.

        Args:
            user_message: User query
            system_prompt: Base system prompt (optional)
            schema_context: Neo4j schema for grounding (optional)

        Yields:
            Token strings as they're generated
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Check provider availability and return status.

        Returns:
            Dict with keys: status, provider, model, error (if any)
        """
        pass


class OllamaProvider(LLMProvider):
    """Local Ollama provider - no data leaves the machine."""

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "qwen2.5:72b"):
        """
        Initialize Ollama provider.

        Args:
            endpoint: Ollama API endpoint
            model: Model name (must be pulled: ollama pull <model>)
        """
        self.endpoint = endpoint.rstrip('/')
        self.model = model

    def _build_full_prompt(self, system_prompt: Optional[str], schema_context: Optional[Dict[str, Any]]) -> str:
        """
        Build complete system prompt with schema grounding.

        Schema context integrated from day one - not bolted on after.
        """
        if schema_context:
            from .schema_context import build_system_prompt
            return build_system_prompt(schema_context, base_prompt=system_prompt)
        return system_prompt or "You are a helpful assistant."

    def complete(self, user_message: str, system_prompt: Optional[str] = None,
                 schema_context: Optional[Dict[str, Any]] = None) -> str:
        """Non-streaming completion with integrated schema grounding."""
        full_prompt = self._build_full_prompt(system_prompt, schema_context)

        try:
            response = requests.post(
                f"{self.endpoint}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": full_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False
                },
                timeout=120
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Ollama request failed: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid Ollama response: {e}")

    def stream(self, user_message: str, system_prompt: Optional[str] = None,
               schema_context: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        """
        Streaming completion with integrated schema grounding.

        Critical for UX at 13 tok/sec generation speed.
        """
        full_prompt = self._build_full_prompt(system_prompt, schema_context)

        try:
            response = requests.post(
                f"{self.endpoint}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": full_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": True
                },
                stream=True,
                timeout=120
            )
            response.raise_for_status()

            # Ollama streams newline-delimited JSON
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            content = chunk["message"]["content"]
                            if content:
                                yield content
                        # Check for completion
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Ollama streaming failed: {e}")

    def health_check(self) -> Dict[str, Any]:
        """Check Ollama availability and list available models."""
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]

            model_available = self.model in models

            return {
                "status": "ok" if model_available else "model_not_found",
                "provider": "ollama",
                "endpoint": self.endpoint,
                "model": self.model,
                "model_available": model_available,
                "available_models": models,
                "hint": f"Pull model with: ollama pull {self.model}" if not model_available else None
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "provider": "ollama",
                "endpoint": self.endpoint,
                "error": str(e),
                "hint": "Is Ollama running? Check: systemctl status ollama"
            }


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider - data leaves institution."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Claude model name
        """
        if not api_key:
            raise ValueError("Anthropic API key required")
        self.api_key = api_key
        self.model = model

        # Lazy import - only load if actually using Anthropic
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("anthropic package required: pip install anthropic")

    def _build_full_prompt(self, system_prompt: Optional[str], schema_context: Optional[Dict[str, Any]]) -> str:
        """Build complete system prompt with schema grounding."""
        if schema_context:
            from .schema_context import build_system_prompt
            return build_system_prompt(schema_context, base_prompt=system_prompt)
        return system_prompt or "You are a helpful assistant."

    def complete(self, user_message: str, system_prompt: Optional[str] = None,
                 schema_context: Optional[Dict[str, Any]] = None) -> str:
        """Non-streaming completion with integrated schema grounding."""
        full_prompt = self._build_full_prompt(system_prompt, schema_context)

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=full_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            return message.content[0].text
        except Exception as e:
            raise ConnectionError(f"Anthropic API error: {e}")

    def stream(self, user_message: str, system_prompt: Optional[str] = None,
               schema_context: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        """Streaming completion with integrated schema grounding."""
        full_prompt = self._build_full_prompt(system_prompt, schema_context)

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2048,
                system=full_prompt,
                messages=[{"role": "user", "content": user_message}]
            ) as stream:
                for text in stream.text_stream:
                    if text:
                        yield text
        except Exception as e:
            raise ConnectionError(f"Anthropic streaming error: {e}")

    def health_check(self) -> Dict[str, Any]:
        """Check API key validity (no actual API call - just returns config)."""
        return {
            "status": "ok",
            "provider": "anthropic",
            "model": self.model,
            "note": "Cloud provider - data leaves institution"
        }


class OpenAIProvider(LLMProvider):
    """OpenAI provider - data leaves institution."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: OpenAI model name
        """
        if not api_key:
            raise ValueError("OpenAI API key required")
        self.api_key = api_key
        self.model = model

        # Lazy import
        try:
            import openai
            self.client = openai.OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai package required: pip install openai")

    def _build_full_prompt(self, system_prompt: Optional[str], schema_context: Optional[Dict[str, Any]]) -> str:
        """Build complete system prompt with schema grounding."""
        if schema_context:
            from .schema_context import build_system_prompt
            return build_system_prompt(schema_context, base_prompt=system_prompt)
        return system_prompt or "You are a helpful assistant."

    def complete(self, user_message: str, system_prompt: Optional[str] = None,
                 schema_context: Optional[Dict[str, Any]] = None) -> str:
        """Non-streaming completion with integrated schema grounding."""
        full_prompt = self._build_full_prompt(system_prompt, schema_context)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            raise ConnectionError(f"OpenAI API error: {e}")

    def stream(self, user_message: str, system_prompt: Optional[str] = None,
               schema_context: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        """Streaming completion with integrated schema grounding."""
        full_prompt = self._build_full_prompt(system_prompt, schema_context)

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": user_message}
                ],
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise ConnectionError(f"OpenAI streaming error: {e}")

    def health_check(self) -> Dict[str, Any]:
        """Check API key validity (no actual API call - just returns config)."""
        return {
            "status": "ok",
            "provider": "openai",
            "model": self.model,
            "note": "Cloud provider - data leaves institution"
        }
