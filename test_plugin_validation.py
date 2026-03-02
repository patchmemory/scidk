#!/usr/bin/env python3
"""
Test plugin validation with SciDKData wrappability check.

Tests:
1. Plugin returning dict passes validation
2. Plugin returning list passes validation
3. Plugin returning DataFrame passes validation
4. Plugin returning invalid type fails validation
5. Plugin with KeyError still passes (context-dependent)
"""
import tempfile
import os


def test_plugin_dict_passes():
    """Test that plugin returning dict passes validation."""
    from scidk.core.scripts import Script
    from scidk.core.script_validators import BaseValidator

    code = """
def run(context):
    return {'status': 'success', 'data': [1, 2, 3]}
"""

    script = Script(
        id='test-dict-plugin',
        name='Test Dict Plugin',
        language='python',
        code=code,
        category='plugins'
    )

    validator = BaseValidator()
    result = validator.validate(script)

    assert result.passed, f"Validation failed: {result.errors}"
    assert result.test_results.get('valid_syntax') == True
    assert result.test_results.get('executes_without_error') == True
    assert result.test_results.get('returns_wrappable_data') == True
    print("✅ Plugin returning dict passes validation")


def test_plugin_list_passes():
    """Test that plugin returning list passes validation."""
    from scidk.core.scripts import Script
    from scidk.core.script_validators import BaseValidator

    code = """
def run(context):
    return [{'name': 'Alice'}, {'name': 'Bob'}]
"""

    script = Script(
        id='test-list-plugin',
        name='Test List Plugin',
        language='python',
        code=code,
        category='plugins'
    )

    validator = BaseValidator()
    result = validator.validate(script)

    assert result.passed, f"Validation failed: {result.errors}"
    assert result.test_results.get('returns_wrappable_data') == True
    print("✅ Plugin returning list passes validation")


def test_plugin_dataframe_passes():
    """Test that plugin returning DataFrame passes validation."""
    from scidk.core.scripts import Script
    from scidk.core.script_validators import BaseValidator

    code = """
def run(context):
    import pandas as pd
    return pd.DataFrame({'col': [1, 2, 3]})
"""

    script = Script(
        id='test-df-plugin',
        name='Test DataFrame Plugin',
        language='python',
        code=code,
        category='plugins'
    )

    validator = BaseValidator()
    result = validator.validate(script)

    assert result.passed, f"Validation failed: {result.errors}"
    assert result.test_results.get('returns_wrappable_data') == True
    print("✅ Plugin returning DataFrame passes validation")


def test_plugin_invalid_type_fails():
    """Test that plugin returning string fails validation."""
    from scidk.core.scripts import Script
    from scidk.core.script_validators import BaseValidator

    code = """
def run(context):
    return "This is a string, not a dict/list/DataFrame"
"""

    script = Script(
        id='test-string-plugin',
        name='Test String Plugin',
        language='python',
        code=code,
        category='plugins'
    )

    validator = BaseValidator()
    result = validator.validate(script)

    assert not result.passed, "Validation should have failed for string return"
    assert result.test_results.get('returns_wrappable_data') == False
    assert any('non-wrappable' in err.lower() or 'unsupported' in err.lower()
               for err in result.errors)
    print("✅ Plugin returning invalid type fails validation")


def test_plugin_keyerror_passes():
    """Test that plugin with KeyError still passes (context-dependent)."""
    from scidk.core.scripts import Script
    from scidk.core.script_validators import BaseValidator

    code = """
def run(context):
    # This will raise KeyError if 'required_key' not in context
    # But validation should pass because we catch KeyError
    return {'data': context['required_key']}
"""

    script = Script(
        id='test-keyerror-plugin',
        name='Test KeyError Plugin',
        language='python',
        code=code,
        category='plugins'
    )

    validator = BaseValidator()
    result = validator.validate(script)

    # Should pass validation because KeyError is caught and treated as OK
    assert result.passed, f"Validation failed: {result.errors}"
    assert result.test_results.get('returns_wrappable_data') == True
    print("✅ Plugin with KeyError passes validation (context-dependent)")


def test_non_plugin_skips_wrappability():
    """Test that scripts without run() skip wrappability test."""
    from scidk.core.scripts import Script
    from scidk.core.script_validators import BaseValidator

    code = """
# Script without run() function (e.g., interpreter)
print("This is not a plugin")
"""

    script = Script(
        id='test-non-plugin',
        name='Test Non-Plugin',
        language='python',
        code=code,
        category='other'
    )

    validator = BaseValidator()
    result = validator.validate(script)

    # Should pass basic tests, wrappability test should be skipped
    assert result.passed, f"Validation failed: {result.errors}"
    assert 'returns_wrappable_data' not in result.test_results
    print("✅ Non-plugin script skips wrappability test")


if __name__ == '__main__':
    print("Testing plugin validation with wrappability check...\n")

    test_plugin_dict_passes()
    test_plugin_list_passes()
    test_plugin_dataframe_passes()
    test_plugin_invalid_type_fails()
    test_plugin_keyerror_passes()
    test_non_plugin_skips_wrappability()

    print("\n✅ All validation tests passed!")
