"""
Universal data types for SciDK plugin system.

Provides SciDKData wrapper for consistent plugin return types.
"""
import json
from typing import Any, Dict, List, Optional, Union


class SciDKData:
    """
    Universal return type for SciDK plugins.

    Wraps common Python types (dict, list, DataFrame) in a consistent interface
    for validation, serialization, and downstream consumption.

    Plugin authors don't need to use this directly - load_plugin() auto-wraps.
    Advanced users can construct explicitly for richer behavior.

    Example (casual user - auto-wrapped):
        def run(context):
            return {'gene': 'BRCA1', 'count': 42}  # Auto-wrapped in SciDKData

    Example (advanced user - explicit):
        from scidk.core.data_types import SciDKData

        def run(context):
            result = SciDKData().from_dataframe(my_df)
            return result
    """

    def __init__(self):
        """Initialize empty SciDKData wrapper."""
        self._data = None
        self._type = None  # 'dict', 'list', 'dataframe', 'json'

    # --- Input methods (accept common Python types) ---

    def from_dict(self, d: dict) -> 'SciDKData':
        """
        Wrap a dictionary.

        Args:
            d: Dictionary to wrap (must be JSON-serializable)

        Returns:
            Self for chaining

        Raises:
            TypeError: If dict is not JSON-serializable
        """
        # Validate JSON-serializable
        try:
            json.dumps(d)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Dict must be JSON-serializable: {e}")

        self._data = d
        self._type = 'dict'
        return self

    def from_list(self, lst: list) -> 'SciDKData':
        """
        Wrap a list.

        Args:
            lst: List to wrap (must be JSON-serializable)

        Returns:
            Self for chaining

        Raises:
            TypeError: If list is not JSON-serializable
        """
        # Validate JSON-serializable
        try:
            json.dumps(lst)
        except (TypeError, ValueError) as e:
            raise TypeError(f"List must be JSON-serializable: {e}")

        self._data = lst
        self._type = 'list'
        return self

    def from_dataframe(self, df) -> 'SciDKData':
        """
        Wrap a pandas DataFrame.

        Args:
            df: pandas DataFrame

        Returns:
            Self for chaining

        Raises:
            ImportError: If pandas not available
            TypeError: If not a DataFrame-like object
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for DataFrame support")

        # Check it's actually a DataFrame (not just has to_dict method)
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df)}")

        self._data = df
        self._type = 'dataframe'
        return self

    def from_json(self, json_str: str) -> 'SciDKData':
        """
        Parse JSON string into SciDKData.

        Args:
            json_str: JSON string to parse

        Returns:
            Self for chaining

        Raises:
            json.JSONDecodeError: If invalid JSON
        """
        parsed = json.loads(json_str)

        if isinstance(parsed, dict):
            return self.from_dict(parsed)
        elif isinstance(parsed, list):
            return self.from_list(parsed)
        else:
            raise TypeError(f"JSON must parse to dict or list, got {type(parsed)}")

    # --- Output methods (serialize to what downstream needs) ---

    def to_dict(self) -> dict:
        """
        Convert to dictionary.

        Returns:
            Dict representation

        Raises:
            ValueError: If data is None
            TypeError: If data type cannot be converted to dict
        """
        if self._data is None:
            raise ValueError("No data to convert")

        if self._type == 'dict':
            return self._data
        elif self._type == 'list':
            # Wrap list in dict for consistency
            return {'data': self._data}
        elif self._type == 'dataframe':
            # Convert DataFrame to dict of records
            return {'data': self._data.to_dict('records')}
        else:
            raise TypeError(f"Cannot convert {self._type} to dict")

    def to_json(self) -> str:
        """
        Serialize to JSON string.

        Returns:
            JSON string representation

        Raises:
            ValueError: If data is None
        """
        if self._data is None:
            raise ValueError("No data to serialize")

        if self._type == 'dict':
            return json.dumps(self._data)
        elif self._type == 'list':
            return json.dumps(self._data)
        elif self._type == 'dataframe':
            return self._data.to_json(orient='records')
        else:
            raise TypeError(f"Cannot serialize {self._type} to JSON")

    def to_list(self) -> list:
        """
        Convert to list.

        Returns:
            List representation

        Raises:
            ValueError: If data is None
        """
        if self._data is None:
            raise ValueError("No data to convert")

        if self._type == 'list':
            return self._data
        elif self._type == 'dict':
            # Wrap dict in list for consistency
            return [self._data]
        elif self._type == 'dataframe':
            return self._data.to_dict('records')
        else:
            raise TypeError(f"Cannot convert {self._type} to list")

    def to_dataframe(self):
        """
        Convert to pandas DataFrame.

        Returns:
            pandas DataFrame

        Raises:
            ImportError: If pandas not available
            ValueError: If data is None
            TypeError: If data cannot be converted to DataFrame
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for DataFrame support")

        if self._data is None:
            raise ValueError("No data to convert")

        if self._type == 'dataframe':
            return self._data
        elif self._type == 'list':
            return pd.DataFrame(self._data)
        elif self._type == 'dict':
            # Try to create DataFrame from dict
            return pd.DataFrame([self._data])
        else:
            raise TypeError(f"Cannot convert {self._type} to DataFrame")

    # --- Utility methods ---

    def is_empty(self) -> bool:
        """Check if data is empty or None."""
        if self._data is None:
            return True

        if self._type == 'dict':
            return len(self._data) == 0
        elif self._type == 'list':
            return len(self._data) == 0
        elif self._type == 'dataframe':
            return self._data.empty

        return True

    def data_type(self) -> Optional[str]:
        """Get the underlying data type."""
        return self._type

    def __repr__(self):
        """String representation."""
        if self._data is None:
            return "SciDKData(empty)"
        return f"SciDKData(type={self._type}, size={self._get_size()})"

    def _get_size(self) -> int:
        """Get size of data for repr."""
        if self._type == 'dict':
            return len(self._data)
        elif self._type == 'list':
            return len(self._data)
        elif self._type == 'dataframe':
            return len(self._data)
        return 0


def auto_wrap(data: Any) -> SciDKData:
    """
    Auto-wrap common Python types in SciDKData.

    Used by load_plugin() to wrap plugin outputs automatically.

    Args:
        data: Plugin output (dict, list, DataFrame, or SciDKData)

    Returns:
        SciDKData wrapper

    Raises:
        TypeError: If data type is not supported
    """
    # Already wrapped
    if isinstance(data, SciDKData):
        return data

    result = SciDKData()

    # Dict (check first - most common)
    if isinstance(data, dict):
        return result.from_dict(data)

    # List
    elif isinstance(data, list):
        return result.from_list(data)

    # DataFrame (improved duck typing - check for DataFrame-specific attributes)
    # Check for .to_dict, .empty, and .columns to avoid false positives
    elif (hasattr(data, 'to_dict') and
          callable(data.to_dict) and
          hasattr(data, 'empty') and
          hasattr(data, 'columns')):
        # Has DataFrame-like interface
        return result.from_dataframe(data)

    # Unsupported
    else:
        raise TypeError(
            f"Plugin returned unsupported type: {type(data).__name__}. "
            f"Plugins must return dict, list, pandas DataFrame, or SciDKData. "
            f"Got: {type(data)}"
        )
