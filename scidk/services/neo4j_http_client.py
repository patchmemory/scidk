"""Small read-only client for the Neo4j HTTP Query API (``/db/<db>/query/v2``).

Built for NExtSEEK-dev, where Bolt is not exposed. It never writes: statements
containing write keywords are refused before any request is made, and every
request carries ``"accessMode": "Read"``.

Credentials come from the environment (``NEXTSEEK_HTTP_URL``, ``NEXTSEEK_USER``,
``NEXTSEEK_PASSWORD``) or explicit arguments. They are never logged and never
included in exception messages.

A Neo4j profile could later use this as an HTTP transport by exposing the same
``query(statement, params) -> list[dict]`` surface that the Bolt-backed client
offers (see ``from_env`` for the construction point). It is intentionally not
wired into Links, Settings or ``get_neo4j_client_for_profile`` yet.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

import requests

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BATCH_SIZE = 1000

ENV_URL = 'NEXTSEEK_HTTP_URL'
ENV_USER = 'NEXTSEEK_USER'
ENV_PASSWORD = 'NEXTSEEK_PASSWORD'

_WRITE_PATTERNS = [
    r'\bCREATE\b', r'\bMERGE\b', r'\bSET\b', r'\bDELETE\b', r'\bREMOVE\b', r'\bDROP\b',
    r'\bLOAD\s+CSV\b', r'\bCALL\b[\s\S]*\bIN\s+TRANSACTIONS\b',
]
_WRITE_RE = re.compile('|'.join(_WRITE_PATTERNS), re.IGNORECASE)
_STRING_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`")
_COMMENT_RE = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/')


class ReadOnlyViolation(ValueError):
    """Raised when a statement contains a write keyword. Nothing is sent."""


class Neo4jHttpError(RuntimeError):
    """Raised for HTTP/API failures. Never contains credentials."""


def check_read_only(statement: str) -> None:
    """Refuse statements with write keywords (string literals and comments ignored)."""
    stripped = _STRING_RE.sub("''", _COMMENT_RE.sub(' ', statement or ''))
    match = _WRITE_RE.search(stripped)
    if match:
        keyword = ' '.join(match.group(0).split()).upper()
        raise ReadOnlyViolation(f'Read-only client refused statement containing {keyword}')


def chunked(items: Sequence[Any], size: int = DEFAULT_BATCH_SIZE) -> Iterator[List[Any]]:
    if size < 1:
        raise ValueError('batch size must be >= 1')
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


class Neo4jHttpClient:
    def __init__(self, url: str, user: str, password: str, database: str = 'neo4j', *,
                 timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
                 backoff: float = 1.0, session: Optional[requests.Session] = None,
                 sleep: Callable[[float], None] = time.sleep, access_mode: bool = True):
        if not url or not user or password is None:
            raise ValueError('url, user and password are required')
        base = url.rstrip('/')
        # Accept either the server root or a full .../db/<name>/query/v2 URL.
        self._endpoint = base if base.endswith('/query/v2') else f'{base}/db/{database}/query/v2'
        self._auth = (user, password)
        self._timeout = timeout
        self._retries = max(1, int(retries))
        self._backoff = backoff
        self._session = session or requests.Session()
        self._sleep = sleep
        self._send_access_mode = access_mode

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None, **kwargs: Any) -> 'Neo4jHttpClient':
        env = os.environ if env is None else env
        missing = [name for name in (ENV_URL, ENV_USER, ENV_PASSWORD) if not env.get(name)]
        if missing:
            raise Neo4jHttpError('Missing environment variables: ' + ', '.join(missing))
        return cls(env[ENV_URL], env[ENV_USER], env[ENV_PASSWORD], **kwargs)

    def __repr__(self) -> str:
        return f'<Neo4jHttpClient {self._endpoint}>'

    def query(self, statement: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        check_read_only(statement)
        body: Dict[str, Any] = {'statement': statement, 'parameters': params or {}}
        if self._send_access_mode:
            body['accessMode'] = 'Read'
        payload = self._post(body)
        return self.parse_response(payload)

    def query_batched(self, statement: str, key: str, values: Sequence[Any],
                      params: Optional[Dict[str, Any]] = None,
                      batch_size: int = DEFAULT_BATCH_SIZE) -> List[Dict[str, Any]]:
        """Run ``statement`` once per batch, passing the batch as ``$<key>``."""
        rows: List[Dict[str, Any]] = []
        for batch in chunked(values, batch_size):
            rows.extend(self.query(statement, dict(params or {}, **{key: batch})))
        return rows

    @staticmethod
    def parse_response(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        errors = payload.get('errors')
        if errors:
            first = errors[0] if isinstance(errors, list) and errors else {}
            raise Neo4jHttpError('Query API error: %s %s' % (first.get('code', ''), first.get('message', '')))
        data = payload.get('data')
        if not isinstance(data, dict) or 'fields' not in data or 'values' not in data:
            raise Neo4jHttpError('Unexpected Query API response shape')
        fields = data['fields']
        return [dict(zip(fields, row)) for row in data['values']]

    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        last: Optional[str] = None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._session.post(
                    self._endpoint, json=body, auth=self._auth, timeout=self._timeout,
                    headers={'Accept': 'application/json'})
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = type(exc).__name__
            else:
                if response.status_code >= 500 and attempt < self._retries:
                    last = f'HTTP {response.status_code}'
                else:
                    return self._decode(response)
            if attempt < self._retries:
                self._sleep(self._backoff * attempt)
        raise Neo4jHttpError(f'Query API unreachable after {self._retries} attempts ({last})')

    @staticmethod
    def _decode(response: Any) -> Dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            if response.status_code == 401:
                raise Neo4jHttpError('Query API rejected credentials (HTTP 401)')
            if isinstance(payload, dict) and payload.get('errors'):
                Neo4jHttpClient.parse_response(payload)
            raise Neo4jHttpError(f'Query API returned HTTP {response.status_code}')
        if not isinstance(payload, dict):
            raise Neo4jHttpError('Query API returned a non-JSON response')
        return payload
