"""One definition of "which user is this request for".

Per-user state — a canvas session, a draft, a preference — is keyed by a string.
Which string had been decided independently at each call site, and
``api_canvas._current_user_id`` showed why that is a problem: it read

    getattr(g, 'scidk_user_id', None) or getattr(g, 'scidk_user', None) or 'anonymous'

which mixes three different kinds of value behind one name. Two consequences,
both silent:

* ``scidk_user_id`` is a database row id and ``scidk_user`` is a username, so the
  key's *meaning* depended on which attributes happened to be set. A path that
  set only the username keyed the same person differently from one that set both.
* ``or`` treats a falsy id as absent. A user whose row id is ``0`` fell through to
  the username, and a user with neither fell through to ``'anonymous'`` — sharing
  one canvas with every other such user.

This module fixes the choice in one place: the database row id when there is one,
coerced to ``str``; the username when there is not; ``'anonymous'`` only when auth
is genuinely off. Row id is preferred over username because it survives a
rename, and because it is what the existing behaviour produced whenever auth was
on — changing the preference would orphan every canvas already saved.
"""
from __future__ import annotations

from typing import Any, Optional

from flask import g

__all__ = ["ANONYMOUS_USER_KEY", "current_user_key", "is_anonymous"]

#: Key used when no user is identified — auth disabled, or a test client. Not a
#: fallback for a *failed* identification: those set one of the attributes below.
ANONYMOUS_USER_KEY = "anonymous"


def current_user_key(default: str = ANONYMOUS_USER_KEY) -> str:
    """Return a stable string identifying the current request's user.

    Reads the attributes ``auth_middleware.before_request`` and
    ``decorators.require_role`` set on ``g``. Safe outside a request context,
    where it returns ``default``.

    Args:
        default: Returned when no user is identified.

    Returns:
        ``str(g.scidk_user_id)`` when set, else ``g.scidk_user``, else ``default``.
        Never an empty string, and never a non-string.
    """
    user_id = _attr("scidk_user_id")
    # `is not None`, not truthiness: a row id of 0 is a user.
    if user_id is not None:
        text = str(user_id).strip()
        if text:
            return text

    username = _attr("scidk_user")
    if isinstance(username, str) and username.strip():
        return username.strip()

    return default


def is_anonymous() -> bool:
    """Whether this request has no identified user."""
    return current_user_key() == ANONYMOUS_USER_KEY


def _attr(name: str) -> Optional[Any]:
    """Read an attribute off ``g``, tolerating no request context at all."""
    try:
        return getattr(g, name, None)
    except RuntimeError:
        # Outside an application context, touching g raises. A background job
        # asking who the user is has its answer: nobody.
        return None
