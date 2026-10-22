"""
LLM Provider Factory - instantiate providers from SciDK settings.

Handles graceful degradation:
- Ollama unreachable → clear error message
- No API keys → prompt to configure
- Invalid provider → helpful error
"""
from typing import Optional, Dict, Any
import os
from .llm_providers import LLMProvider, OllamaProvider, AnthropicProvider, OpenAIProvider


class LLMProviderFactory:
    """Factory to create LLM providers from settings or environment."""

    @staticmethod
    def for_request(settings: Optional[Dict[str, Any]] = None) -> LLMProvider:
        """The provider for the current request's user: their own OpenAI-compatible
        setting (Settings → AI) if they have one, else the legacy settings/env.

        An explicit ``provider`` in the request body still selects a legacy
        provider. Not settings['chat_llm_provider']: the call sites fill that
        from SCIDK_CHAT_LLM_PROVIDER or default it to 'ollama', so it is never
        empty and would always win over the user's own setting.
        """
        settings = settings or {}
        try:
            from flask import current_app, g, has_request_context, request
            if has_request_context() and not (request.get_json(silent=True) or {}).get('provider'):
                from .provider_settings import provider_for
                db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
                provider = provider_for(db, getattr(g, 'scidk_user', None) or '')
                if provider is not None:
                    return provider
        except Exception as e:  # noqa: BLE001 - fall back to the legacy path
            import logging
            logging.getLogger(__name__).warning("User LLM setting unusable, using legacy provider: %s", e)
        return LLMProviderFactory.from_settings(settings)

    @staticmethod
    def from_settings(settings: Optional[Dict[str, Any]] = None) -> LLMProvider:
        """
        Build provider from settings dict or environment variables.

        Priority: settings dict > environment variables > defaults

        Args:
            settings: Optional settings dictionary. If None, uses environment.

        Returns:
            Configured LLMProvider instance

        Raises:
            ValueError: If provider type unknown or missing required config
            ConnectionError: If provider unreachable (for Ollama)

        Settings keys:
            chat_llm_provider: 'ollama' | 'anthropic' | 'openai'
            chat_ollama_endpoint: http://localhost:11434
            chat_ollama_model: qwen2.5:72b
            chat_claude_api_key: sk-ant-...
            chat_claude_model: claude-sonnet-4-6
            chat_openai_api_key: sk-...
            chat_openai_model: gpt-4o
        """
        settings = settings or {}

        # Determine provider type
        provider_type = (
            settings.get('chat_llm_provider') or
            os.environ.get('SCIDK_CHAT_LLM_PROVIDER') or
            os.environ.get('SCIDK_GRAPHRAG_LLM_PROVIDER') or  # Legacy compat
            'ollama'  # Default to local
        ).strip().lower()

        # Ollama (local)
        if provider_type in ('ollama', 'local_ollama', 'local'):
            endpoint = (
                settings.get('chat_ollama_endpoint') or
                os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT') or
                'http://localhost:11434'
            )
            model = (
                settings.get('chat_ollama_model') or
                os.environ.get('SCIDK_CHAT_OLLAMA_MODEL') or
                os.environ.get('SCIDK_GRAPHRAG_MODEL') or  # Legacy compat
                'qwen2.5:72b'
            )

            provider = OllamaProvider(endpoint=endpoint, model=model)

            # Health check on creation to fail fast if Ollama not running
            health = provider.health_check()
            if health["status"] == "error":
                raise ConnectionError(
                    f"Ollama not available at {endpoint}. "
                    f"Error: {health['error']}. "
                    f"Hint: {health.get('hint', 'Check Ollama installation')}"
                )
            if health["status"] == "model_not_found":
                raise ValueError(
                    f"Model '{model}' not found. "
                    f"Available models: {', '.join(health['available_models'])}. "
                    f"Pull with: ollama pull {model}"
                )

            return provider

        # Anthropic Claude
        elif provider_type in ('anthropic', 'claude'):
            api_key = (
                settings.get('chat_claude_api_key') or
                os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY') or
                os.environ.get('ANTHROPIC_API_KEY')
            )
            if not api_key:
                raise ValueError(
                    "Anthropic API key required. Set in Settings → Chat or environment: "
                    "SCIDK_CHAT_CLAUDE_API_KEY"
                )

            model = (
                settings.get('chat_claude_model') or
                os.environ.get('SCIDK_CHAT_CLAUDE_MODEL') or
                'claude-sonnet-4-6'
            )

            return AnthropicProvider(api_key=api_key, model=model)

        # OpenAI
        elif provider_type in ('openai', 'gpt'):
            api_key = (
                settings.get('chat_openai_api_key') or
                os.environ.get('SCIDK_CHAT_OPENAI_API_KEY') or
                os.environ.get('OPENAI_API_KEY')
            )
            if not api_key:
                raise ValueError(
                    "OpenAI API key required. Set in Settings → Chat or environment: "
                    "SCIDK_CHAT_OPENAI_API_KEY"
                )

            model = (
                settings.get('chat_openai_model') or
                os.environ.get('SCIDK_CHAT_OPENAI_MODEL') or
                'gpt-4o'
            )

            return OpenAIProvider(api_key=api_key, model=model)

        else:
            raise ValueError(
                f"Unknown provider: '{provider_type}'. "
                f"Valid options: ollama, anthropic, openai"
            )

    @staticmethod
    def get_available_providers(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Check which providers are configured and available.

        Returns dict of {provider_name: {status, details...}}

        Useful for UI to show available provider options.
        """
        settings = settings or {}
        providers = {}

        # Check Ollama
        try:
            endpoint = (
                settings.get('chat_ollama_endpoint') or
                os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT') or
                'http://localhost:11434'
            )
            model = (
                settings.get('chat_ollama_model') or
                os.environ.get('SCIDK_CHAT_OLLAMA_MODEL') or
                'qwen2.5:72b'
            )
            ollama = OllamaProvider(endpoint=endpoint, model=model)
            providers['ollama'] = ollama.health_check()
        except Exception as e:
            providers['ollama'] = {"status": "error", "error": str(e)}

        # Check Anthropic
        api_key = (
            settings.get('chat_claude_api_key') or
            os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY') or
            os.environ.get('ANTHROPIC_API_KEY')
        )
        if api_key:
            model = settings.get('chat_claude_model') or 'claude-sonnet-4-6'
            try:
                anthropic = AnthropicProvider(api_key=api_key, model=model)
                providers['anthropic'] = anthropic.health_check()
            except Exception as e:
                providers['anthropic'] = {"status": "error", "error": str(e)}
        else:
            providers['anthropic'] = {
                "status": "not_configured",
                "hint": "Set SCIDK_CHAT_CLAUDE_API_KEY to enable"
            }

        # Check OpenAI
        api_key = (
            settings.get('chat_openai_api_key') or
            os.environ.get('SCIDK_CHAT_OPENAI_API_KEY') or
            os.environ.get('OPENAI_API_KEY')
        )
        if api_key:
            model = settings.get('chat_openai_model') or 'gpt-4o'
            try:
                openai = OpenAIProvider(api_key=api_key, model=model)
                providers['openai'] = openai.health_check()
            except Exception as e:
                providers['openai'] = {"status": "error", "error": str(e)}
        else:
            providers['openai'] = {
                "status": "not_configured",
                "hint": "Set SCIDK_CHAT_OPENAI_API_KEY to enable"
            }

        return providers
