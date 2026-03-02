"""Integration tests for transparency layer dependency tracking.

Tests the AST-based dependency extraction and dependency management
in ScriptsManager for the transparency layer architecture.

Coverage targets:
- scidk/core/script_validators.py: extract_plugin_dependencies()
- scidk/core/scripts.py: dependency management methods
"""
import pytest
from scidk.core.script_validators import extract_plugin_dependencies
from scidk.core.scripts import ScriptsManager, Script

# Fixtures are auto-discovered via pytest_plugins in conftest.py
# No explicit imports needed


class TestDependencyExtraction:
    """Test AST-based dependency extraction from code."""

    def test_extract_dependencies_single_plugin(self):
        """Test extracting a single load_plugin call."""
        code = """
def run(context):
    data = load_plugin('normalizer', manager, context)
    return data
"""
        deps = extract_plugin_dependencies(code)
        assert deps == ['normalizer'], f"Expected ['normalizer'], got {deps}"

    def test_extract_dependencies_multiple_plugins(self):
        """Test extracting multiple load_plugin calls."""
        code = """
def run(context):
    norm = load_plugin('normalizer', manager, context)
    parser = load_plugin('parser', manager, context)
    validator = load_plugin('validator', manager, context)
    return norm, parser, validator
"""
        deps = extract_plugin_dependencies(code)
        assert set(deps) == {'normalizer', 'parser', 'validator'}, \
            f"Expected 3 plugins, got {deps}"

    def test_extract_dependencies_no_plugins(self):
        """Test code with no load_plugin calls."""
        code = """
def run(context):
    result = {'key': 'value'}
    return result
"""
        deps = extract_plugin_dependencies(code)
        assert deps == [], f"Expected no dependencies, got {deps}"

    def test_extract_dependencies_with_comments(self):
        """Test extraction ignores commented load_plugin calls."""
        code = """
def run(context):
    # This is commented: load_plugin('commented', manager, context)
    data = load_plugin('real_plugin', manager, context)
    return data
"""
        deps = extract_plugin_dependencies(code)
        assert deps == ['real_plugin'], f"Should ignore commented calls, got {deps}"

    def test_extract_dependencies_nested_calls(self):
        """Test extraction from nested function calls."""
        code = """
def run(context):
    result = process_data(load_plugin('nested', manager, context))
    return result
"""
        deps = extract_plugin_dependencies(code)
        assert deps == ['nested'], f"Should extract from nested calls, got {deps}"

    def test_extract_dependencies_invalid_syntax(self):
        """Test extraction with syntax errors returns empty list."""
        code = """
def run(context)
    # Missing colon - syntax error
    load_plugin('plugin', manager)
"""
        deps = extract_plugin_dependencies(code)
        assert deps == [], "Should return empty list for invalid syntax"


class TestDependencyManagement:
    """Test dependency management in ScriptsManager."""

    def test_dependencies_written_on_validation(self, scripts_manager, test_interpreter_with_plugin):
        """Test dependencies saved when script validated."""
        deps = scripts_manager.get_dependencies('test_interpreter_alpha')
        assert 'test_plugin_alpha' in deps, \
            f"Expected plugin dependency, got {deps}"

    def test_dependencies_cleared_on_edit(self, scripts_manager, test_interpreter_with_plugin):
        """Test dependencies removed when script edited."""
        # Edit the script
        script = scripts_manager.get_script('test_interpreter_alpha')
        original_code = script.code
        script.code = original_code + "\n# edited"
        scripts_manager.update_script(script)

        # Dependencies should be cleared
        deps = scripts_manager.get_dependencies('test_interpreter_alpha')
        assert deps == [], f"Expected no dependencies after edit, got {deps}"

        # Verify validation status reset
        updated_script = scripts_manager.get_script('test_interpreter_alpha')
        assert updated_script.validation_status == 'draft', \
            "Script should be draft after edit"

    def test_dependencies_updated_on_revalidation(self, scripts_manager, test_interpreter_with_plugin):
        """Test dependencies refresh when script re-validated."""
        # Edit and clear dependencies
        script = scripts_manager.get_script('test_interpreter_alpha')
        script.code += "\n# edited"
        scripts_manager.update_script(script)

        # Verify cleared
        deps = scripts_manager.get_dependencies('test_interpreter_alpha')
        assert deps == []

        # Simulate re-validation: extract dependencies and write them
        # (In production, validation service would do this)
        from scidk.core.script_validators import extract_plugin_dependencies
        dependencies = extract_plugin_dependencies(script.code)
        scripts_manager.write_dependencies(script.id, 'interpreter', dependencies)

        # Dependencies should be restored
        deps = scripts_manager.get_dependencies('test_interpreter_alpha')
        assert 'test_plugin_alpha' in deps, \
            "Dependencies should be restored after revalidation"

    def test_get_dependents_returns_correct_scripts(self, scripts_manager, test_interpreter_with_plugin):
        """Test get_dependents returns scripts using a plugin."""
        dependents = scripts_manager.get_dependents('test_plugin_alpha')

        assert len(dependents) == 1, f"Expected 1 dependent, got {len(dependents)}"
        assert dependents[0]['id'] == 'test_interpreter_alpha'
        assert dependents[0]['type'] == 'interpreter'  # Type matches script category (singular)

    def test_multiple_dependents(self, scripts_manager, test_interpreter_with_plugin, test_interpreter_multi_plugin):
        """Test plugin with multiple dependents."""
        dependents = scripts_manager.get_dependents('test_plugin_alpha')

        assert len(dependents) == 2, f"Expected 2 dependents, got {len(dependents)}"

        dependent_ids = {d['id'] for d in dependents}
        assert 'test_interpreter_alpha' in dependent_ids
        assert 'test_interpreter_multi' in dependent_ids

    def test_multiple_dependencies(self, scripts_manager, test_interpreter_multi_plugin):
        """Test script with multiple plugin dependencies."""
        deps = scripts_manager.get_dependencies('test_interpreter_multi')

        assert len(deps) == 2, f"Expected 2 dependencies, got {len(deps)}"
        assert 'test_plugin_alpha' in deps
        assert 'test_plugin_beta' in deps

    def test_clear_dependencies(self, scripts_manager, test_interpreter_with_plugin):
        """Test manual dependency clearing."""
        # Verify dependencies exist
        deps = scripts_manager.get_dependencies('test_interpreter_alpha')
        assert len(deps) > 0

        # Clear dependencies
        scripts_manager.clear_dependencies('test_interpreter_alpha')

        # Verify cleared
        deps = scripts_manager.get_dependencies('test_interpreter_alpha')
        assert deps == [], "Dependencies should be cleared"

    def test_no_dependencies_for_unvalidated_script(self, scripts_manager, test_plugin):
        """Test draft scripts don't appear in dependents."""
        # Create unvalidated script that uses plugin
        draft_code = '''
def interpret_file(file_path, manager, context=None):
    result = load_plugin('test_plugin_alpha', manager, context)
    return {'entity_type': 'Draft', 'metadata': {}}
'''

        draft_script = Script(
            id='draft_interpreter',
            name='Draft Interpreter',
            code=draft_code,
            category='interpreters',
            language='python'
        )

        scripts_manager.create_script(draft_script)
        # Do NOT validate

        # Plugin should not show draft as dependent
        dependents = scripts_manager.get_dependents('test_plugin_alpha')
        dependent_ids = {d['id'] for d in dependents}

        assert 'draft_interpreter' not in dependent_ids, \
            "Draft scripts should not appear in dependents"
