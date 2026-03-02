"""
Plugin loader for secure execution of validated plugin scripts.

Provides safe loading and execution of plugins with validation checks
and sandbox isolation.
"""
import json
from typing import Any, Dict, Optional, TYPE_CHECKING

from .script_sandbox import run_sandboxed
from .data_types import SciDKData, auto_wrap

if TYPE_CHECKING:
    from .scripts import ScriptsManager


class PluginLoadError(Exception):
    """Raised when plugin cannot be loaded or executed."""
    pass


def load_plugin(
    plugin_id: str,
    manager: 'ScriptsManager',
    context: Optional[Dict[str, Any]] = None,
    timeout: int = 10
) -> SciDKData:
    """
    Securely load and execute a validated plugin script.

    This is the recommended way to call plugins from other scripts (interpreters, links).
    Only validated + active plugins can be loaded.

    Args:
        plugin_id: Plugin script ID to load
        manager: ScriptsManager instance
        context: Optional context dict to pass to plugin
        timeout: Execution timeout in seconds (default: 10)

    Returns:
        SciDKData wrapper containing plugin result.
        Call .to_dict(), .to_list(), or .to_dataframe() to extract data.

    Raises:
        PluginLoadError: If plugin not found, not validated, not active, or execution fails
        TypeError: If plugin returns unsupported data type

    Example:
        >>> from scidk.core.scripts import ScriptsManager
        >>> from scidk.core.script_plugin_loader import load_plugin
        >>>
        >>> manager = ScriptsManager()
        >>> result = load_plugin('my-plugin-id', manager, {'param': 'value'})
        >>> data = result.to_dict()  # Extract as dict
        >>> print(data['status'], data['data'])
    """
    # 1. Get plugin script
    script = manager.get_script(plugin_id)

    if not script:
        raise PluginLoadError(f"Plugin not found: {plugin_id}")

    # 2. Verify is_active=True and validation_status='validated'
    if script.validation_status != 'validated':
        raise PluginLoadError(
            f"Plugin '{script.name}' (ID: {plugin_id}) is not validated. "
            f"Current status: {script.validation_status}. "
            f"Please validate the plugin in the Scripts page before using it."
        )

    if not script.is_active:
        raise PluginLoadError(
            f"Plugin '{script.name}' (ID: {plugin_id}) is not active. "
            f"Please activate the plugin in the Scripts page before using it."
        )

    # 3. Prepare execution code that outputs result as JSON to stdout
    context_json = json.dumps(context or {})

    execution_code = f"""
import json

# Plugin context
context = {context_json}

# Plugin code
{script.code}

# Execute plugin and output result as JSON
result = run(context)
print(json.dumps(result))
"""

    # 4. Run in sandbox using run_sandboxed()
    sandbox_result = run_sandboxed(execution_code, timeout=timeout)

    if sandbox_result['returncode'] != 0:
        error_msg = sandbox_result['stderr'][:500]  # Limit error length
        raise PluginLoadError(
            f"Plugin '{script.name}' execution failed: {error_msg}"
        )

    if sandbox_result['timed_out']:
        raise PluginLoadError(
            f"Plugin '{script.name}' timed out after {timeout}s. "
            f"Consider optimizing the plugin or increasing timeout."
        )

    # 5. Parse stdout as JSON (MVP contract)
    try:
        raw_result = json.loads(sandbox_result['stdout'])
    except json.JSONDecodeError as e:
        raise PluginLoadError(
            f"Plugin '{script.name}' returned invalid JSON. "
            f"Output: {sandbox_result['stdout'][:200]}"
        )

    # 6. Auto-wrap result in SciDKData
    try:
        wrapped_result = auto_wrap(raw_result)
    except TypeError as e:
        raise PluginLoadError(
            f"Plugin '{script.name}' returned invalid data type: {e}"
        )

    # 7. Return wrapped result
    return wrapped_result


def list_available_plugins(manager: 'ScriptsManager') -> list:
    """
    List all available (validated + active) plugins.

    Args:
        manager: ScriptsManager instance

    Returns:
        List of dicts with plugin metadata:
        - id, name, description, docstring, parameters, category
    """
    all_scripts = manager.list_scripts(category='plugins')

    # Filter for validated + active plugins
    available = [
        s for s in all_scripts
        if s.validation_status == 'validated' and s.is_active
    ]

    # Return metadata only (not code)
    return [
        {
            'id': s.id,
            'name': s.name,
            'description': s.description,
            'docstring': s.docstring,
            'parameters': s.parameters,
            'category': s.category,
            'tags': s.tags
        }
        for s in available
    ]


def validate_plugin_result(result: Any) -> bool:
    """
    Validate that plugin result meets contract requirements.

    Args:
        result: Plugin return value

    Returns:
        True if valid, False otherwise
    """
    # Must be a dict
    if not isinstance(result, dict):
        return False

    # Must have 'status' key (optional for base contract, but recommended)
    # This is a soft check - doesn't raise error, just returns False
    if 'status' not in result:
        return False

    # Must be JSON-serializable (MVP requirement)
    try:
        json.dumps(result)
        return True
    except (TypeError, ValueError):
        return False
