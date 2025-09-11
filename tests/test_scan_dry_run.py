from pathlib import Path

def test_scan_dry_run_basic(client, tmp_path: Path):
    # Setup files
    (tmp_path / 'a.txt').write_text('a', encoding='utf-8')
    (tmp_path / 'b.tmp').write_text('x', encoding='utf-8')
    (tmp_path / 'dir').mkdir()
    (tmp_path / 'dir' / 'c.py').write_text('print(1)\n', encoding='utf-8')
    (tmp_path / '.scidkignore').write_text('# ignore tmp files\n*.tmp\n', encoding='utf-8')

    # No filters: .scidkignore should drop b.tmp
    r = client.post('/api/scan/dry-run', json={'path': str(tmp_path)})
    assert r.status_code == 200
    j = r.get_json()
    assert j['status'] == 'ok'
    assert j['files'] == ['a.txt', 'dir/c.py']  # deterministic ordering
    assert j['total_files'] == 2

    # Include only *.py
    r2 = client.post('/api/scan/dry-run', json={'path': str(tmp_path), 'include': ['**/*.py', '*.py']})
    assert r2.status_code == 200
    j2 = r2.get_json()
    assert j2['files'] == ['dir/c.py']

    # Exclude using pattern
    r3 = client.post('/api/scan/dry-run', json={'path': str(tmp_path), 'exclude': ['**/*.py']})
    assert r3.status_code == 200
    j3 = r3.get_json()
    assert j3['files'] == ['a.txt']

    # Depth limit: max_depth=1 should include a.txt and dir/c.py (depth of c.py is 2 counting root->dir->c.py), so exclude it
    r4 = client.post('/api/scan/dry-run', json={'path': str(tmp_path), 'max_depth': 1})
    assert r4.status_code == 200
    j4 = r4.get_json()
    assert j4['files'] == ['a.txt']
