from scidk.core.graph import InMemoryGraph


def test_upsert_and_get_by_id():
    g = InMemoryGraph()
    dataset = {
        'path': '/tmp/file.txt',
        'filename': 'file.txt',
        'extension': '.txt',
        'size_bytes': 123,
        'created': 1.0,
        'modified': 1.0,
        'mime_type': 'text/plain',
        'checksum': 'abc123',
        'lifecycle_state': 'active'
    }
    ds1 = g.upsert_dataset(dataset)
    assert ds1['id']
    # second upsert should update but not duplicate
    dataset2 = dataset.copy()
    dataset2['size_bytes'] = 456
    ds2 = g.upsert_dataset(dataset2)
    assert ds2['size_bytes'] == 456
    assert len(g.datasets) == 1

    # lookup by id
    fetched = g.get_dataset(ds1['id'])
    assert fetched is not None
    assert fetched['checksum'] == 'abc123'


def test_add_interpretation():
    g = InMemoryGraph()
    dataset = {
        'path': '/tmp/file.py',
        'filename': 'file.py',
        'extension': '.py',
        'size_bytes': 1,
        'created': 1.0,
        'modified': 1.0,
        'mime_type': 'text/x-python',
        'checksum': 'xyz789',
        'lifecycle_state': 'active'
    }
    ds = g.upsert_dataset(dataset)
    g.add_interpretation('xyz789', 'python_code', {'status': 'success', 'data': {'ok': True}})
    assert 'python_code' in ds['interpretations']
    assert ds['interpretations']['python_code']['status'] == 'success'
