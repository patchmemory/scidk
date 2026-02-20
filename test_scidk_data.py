#!/usr/bin/env python3
"""
Quick test script for SciDKData implementation.

Tests:
1. SciDKData wrapping of dict, list, DataFrame
2. Conversions between types
3. auto_wrap() function
4. Duck typing for DataFrames
"""

def test_dict_wrapping():
    """Test dict wrapping and conversion."""
    from scidk.core.data_types import SciDKData

    data = {'status': 'success', 'count': 42}
    wrapped = SciDKData().from_dict(data)

    assert wrapped.to_dict() == data
    assert wrapped.to_list() == [data]
    assert wrapped.data_type() == 'dict'
    assert not wrapped.is_empty()
    print("✅ Dict wrapping and conversion works")


def test_list_wrapping():
    """Test list wrapping and conversion."""
    from scidk.core.data_types import SciDKData

    data = [{'name': 'Alice'}, {'name': 'Bob'}]
    wrapped = SciDKData().from_list(data)

    assert wrapped.to_list() == data
    assert wrapped.to_dict() == {'data': data}
    assert wrapped.data_type() == 'list'
    assert not wrapped.is_empty()
    print("✅ List wrapping and conversion works")


def test_dataframe_wrapping():
    """Test DataFrame wrapping and conversion."""
    from scidk.core.data_types import SciDKData
    try:
        import pandas as pd
    except ImportError:
        print("⚠️  pandas not available, skipping DataFrame tests")
        return

    df = pd.DataFrame({'gene': ['BRCA1', 'TP53'], 'count': [42, 37]})
    wrapped = SciDKData().from_dataframe(df)

    assert wrapped.data_type() == 'dataframe'
    assert not wrapped.is_empty()

    # Convert to dict
    as_dict = wrapped.to_dict()
    assert 'data' in as_dict
    assert len(as_dict['data']) == 2

    # Convert to list
    as_list = wrapped.to_list()
    assert len(as_list) == 2
    assert as_list[0]['gene'] == 'BRCA1'

    # Convert back to DataFrame
    as_df = wrapped.to_dataframe()
    assert len(as_df) == 2
    assert list(as_df.columns) == ['gene', 'count']

    print("✅ DataFrame wrapping and conversion works")


def test_auto_wrap():
    """Test auto_wrap function."""
    from scidk.core.data_types import auto_wrap

    # Test dict
    dict_data = {'key': 'value'}
    wrapped_dict = auto_wrap(dict_data)
    assert wrapped_dict.data_type() == 'dict'

    # Test list
    list_data = [1, 2, 3]
    wrapped_list = auto_wrap(list_data)
    assert wrapped_list.data_type() == 'list'

    # Test DataFrame
    try:
        import pandas as pd
        df_data = pd.DataFrame({'col': [1, 2]})
        wrapped_df = auto_wrap(df_data)
        assert wrapped_df.data_type() == 'dataframe'
    except ImportError:
        pass

    print("✅ auto_wrap function works")


def test_duck_typing():
    """Test improved duck typing for DataFrames."""
    from scidk.core.data_types import auto_wrap

    # Test that dict with to_dict method doesn't get detected as DataFrame
    class FakeDataFrame:
        def to_dict(self):
            return {}

    try:
        fake = FakeDataFrame()
        wrapped = auto_wrap(fake)
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "unsupported type" in str(e).lower()
        print("✅ Duck typing correctly rejects non-DataFrames")


def test_json_serializability():
    """Test JSON serialization validation."""
    from scidk.core.data_types import SciDKData
    import json

    # Valid JSON-serializable dict
    valid_data = {'status': 'success', 'count': 42, 'items': [1, 2, 3]}
    wrapped = SciDKData().from_dict(valid_data)
    json_str = wrapped.to_json()
    assert json.loads(json_str) == valid_data

    # Invalid non-JSON-serializable dict (has function)
    try:
        invalid_data = {'func': lambda x: x}
        wrapped = SciDKData().from_dict(invalid_data)
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "JSON-serializable" in str(e)
        print("✅ JSON-serializability validation works")


def test_empty_data():
    """Test empty data handling."""
    from scidk.core.data_types import SciDKData

    # Empty dict
    empty_dict = SciDKData().from_dict({})
    assert empty_dict.is_empty()

    # Empty list
    empty_list = SciDKData().from_list([])
    assert empty_list.is_empty()

    print("✅ Empty data detection works")


if __name__ == '__main__':
    print("Testing SciDKData implementation...\n")

    test_dict_wrapping()
    test_list_wrapping()
    test_dataframe_wrapping()
    test_auto_wrap()
    test_duck_typing()
    test_json_serializability()
    test_empty_data()

    print("\n✅ All tests passed!")
