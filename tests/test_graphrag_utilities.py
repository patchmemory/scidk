from scidk.services.graphrag_schema import parse_ttl, filter_schema

def test_parse_ttl_variants():
    assert parse_ttl(None) == 0
    assert parse_ttl("3600") == 3600
    assert parse_ttl("5m") == 300
    assert parse_ttl("2h") == 7200
    assert parse_ttl("1d") == 86400
    assert parse_ttl("bad") == 0


def test_filter_schema_allow_deny_and_props():
    raw = {"labels": ["File","Folder","Secret"], "relationships": ["CONTAINS"]}
    filtered = filter_schema(raw, allow_labels=["File","Folder"], deny_labels=["Secret"], prop_exclude=[".*token.*"]) 
    assert set(filtered["labels"]) == {"File","Folder"}
    assert filtered["relationships"] == ["CONTAINS"]
    assert any('token' in pat for pat in filtered["property_exclude"])