from typing import Any, Mapping, Sequence


def assert_json(resp, *, shape: Any = None):
    """
    Assert that a Flask Response has JSON with optional shape checks.
    If shape is a type (e.g., list or dict), assert isinstance(data, shape).
    If shape is a callable, call it with the data for custom assertions.
    """
    assert resp is not None, "No response provided"
    assert hasattr(resp, 'status_code'), "Response missing status_code"
    assert 200 <= resp.status_code < 300, f"Expected 2xx, got {resp.status_code}"
    data = resp.get_json()
    if shape is None:
        return data
    if isinstance(shape, type):
        assert isinstance(data, shape), f"Expected JSON type {shape}, got {type(data)}"
        return data
    if callable(shape):
        shape(data)
        return data
    return data


def assert_error(resp, code: Any = None):
    """
    Assert a JSON error response. Optionally check error code field.
    Accepts Flask test client response objects.
    """
    assert resp is not None
    assert resp.status_code >= 400, f"Expected error status, got {resp.status_code}"
    data = resp.get_json()
    assert isinstance(data, dict), f"Expected JSON error object, got {type(data)}"
    if code is not None:
        observed = data.get('code') or data.get('error') or data.get('type')
        assert str(observed) == str(code), f"Expected error code {code}, got {observed}"
    return data
