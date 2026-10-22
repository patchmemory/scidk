"""One client for any OpenAI-compatible endpoint: Parley, OpenAI, local Ollama (/v1).

Plain HTTP (requests) rather than the openai SDK: the request/response mapping
stays in this one file, so another provider is easy to swap in, and Parley's
extras are visible without SDK model quirks:
- ``finish_reason: "content_filter"`` comes back as a 200 with ``content: null``
  and a ``refusal`` string; it's returned as ``refusal``, not raised.
- newer Claude models return ``message.thinking``; it's kept out of ``content``.
- ``x-parley-v1-cost`` / ``x-parley-v1-request-id`` headers are returned so a
  chat turn can record what it cost.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Generator, List, Optional

import requests

from .llm_providers import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8192   # thinking models spend part of it before answering
TIMEOUT_S = 120


class ProviderError(RuntimeError):
    """The endpoint answered with an error, or couldn't be reached."""


def _headers(api_key: Optional[str]) -> Dict[str, str]:
    h = {'Content-Type': 'application/json'}
    if api_key:
        h['Authorization'] = f'Bearer {api_key}'
    return h


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip('/') + path


def _raise_for(resp: requests.Response) -> None:
    if resp.ok:
        return
    try:
        detail = resp.json().get('error')
        detail = detail.get('message') if isinstance(detail, dict) else detail
    except ValueError:
        detail = resp.text[:300]
    hint = ' (check the API key)' if resp.status_code in (401, 403) else ''
    raise ProviderError(f'HTTP {resp.status_code}{hint}: {detail or resp.reason}')


def list_models(base_url: str, api_key: Optional[str], timeout: float = 20) -> List[str]:
    try:
        resp = requests.get(_url(base_url, '/models'), headers=_headers(api_key), timeout=timeout)
    except requests.RequestException as e:
        raise ProviderError(f'Could not reach {base_url}: {e}') from e
    _raise_for(resp)
    data = resp.json()
    items = data.get('data', data.get('models', [])) if isinstance(data, dict) else data
    return sorted({(m.get('id') or m.get('name')) if isinstance(m, dict) else str(m) for m in items} - {None})


def chat_completion(base_url: str, api_key: Optional[str], model: str,
                    messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
                    max_tokens: int = DEFAULT_MAX_TOKENS, timeout: float = TIMEOUT_S,
                    **extra: Any) -> Dict[str, Any]:
    """One non-streaming turn. Returns {content, tool_calls, finish_reason, refusal,
    usage, cost, request_id, model, raw_message}."""
    body: Dict[str, Any] = {'model': model, 'messages': messages, 'max_tokens': max_tokens, **extra}
    if tools:
        body['tools'] = tools
    started = time.time()
    try:
        resp = requests.post(_url(base_url, '/chat/completions'), headers=_headers(api_key),
                             data=json.dumps(body), timeout=timeout)
    except requests.RequestException as e:
        raise ProviderError(f'Could not reach {base_url}: {e}') from e
    _raise_for(resp)
    data = resp.json()
    choice = (data.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    usage = data.get('usage') or {}
    # One line per call, for spending visibility; never the messages or the key.
    logger.info('llm_call model=%s prompt_tokens=%s completion_tokens=%s cost=%s request_id=%s '
                'finish=%s ms=%d', data.get('model') or model, usage.get('prompt_tokens'),
                usage.get('completion_tokens'), resp.headers.get('x-parley-v1-cost'),
                resp.headers.get('x-parley-v1-request-id'), choice.get('finish_reason'),
                (time.time() - started) * 1000)
    return {
        'content': message.get('content'),
        'tool_calls': message.get('tool_calls') or [],
        'finish_reason': choice.get('finish_reason'),
        'refusal': message.get('refusal'),
        'usage': data.get('usage') or {},
        'cost': resp.headers.get('x-parley-v1-cost'),
        'request_id': resp.headers.get('x-parley-v1-request-id'),
        'model': data.get('model') or model,
        # what to append to the conversation before tool results: no thinking
        'raw_message': {k: v for k, v in message.items() if k != 'thinking'},
    }


class OpenAICompatibleProvider(LLMProvider):
    """LLMProvider over chat_completion, so the existing chat routes can use the
    one provider setting (and the v1/v2 benchmark can run through Parley)."""

    def __init__(self, base_url: str, api_key: Optional[str], model: str, label: str = 'openai_compatible'):
        if not base_url or not model:
            raise ValueError('An OpenAI-compatible provider needs a base URL and a model')
        self.base_url, self.api_key, self.model, self.label = base_url, api_key, model, label
        self.last_turn: Dict[str, Any] = {}

    def _messages(self, user_message, system_prompt, schema_context):
        if schema_context:
            from .schema_context import build_system_prompt
            system_prompt = build_system_prompt(schema_context, base_prompt=system_prompt)
        return [{'role': 'system', 'content': system_prompt or 'You are a helpful assistant.'},
                {'role': 'user', 'content': user_message}]

    def complete(self, user_message: str, system_prompt: Optional[str] = None,
                 schema_context: Optional[Dict[str, Any]] = None) -> str:
        try:
            turn = chat_completion(self.base_url, self.api_key, self.model,
                                   self._messages(user_message, system_prompt, schema_context))
        except ProviderError as e:
            raise ConnectionError(f'{self.label} error: {e}') from e
        self.last_turn = {k: turn[k] for k in ('usage', 'cost', 'request_id', 'finish_reason', 'model')}
        if turn['finish_reason'] == 'content_filter' or (turn['content'] is None and turn['refusal']):
            return f"[The model declined to answer: {turn['refusal'] or 'content filter'}]"
        return turn['content'] or ''

    def stream(self, user_message: str, system_prompt: Optional[str] = None,
               schema_context: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        # One chunk: the callers only concatenate, and a non-streamed turn
        # keeps the refusal and cost handling in one place.
        yield self.complete(user_message, system_prompt, schema_context)

    def health_check(self) -> Dict[str, Any]:
        try:
            models = list_models(self.base_url, self.api_key)
        except ProviderError as e:
            return {'status': 'error', 'provider': self.label, 'error': str(e)}
        status = 'ok' if not models or self.model in models else 'model_not_found'
        return {'status': status, 'provider': self.label, 'model': self.model,
                'available_models': models[:50]}
