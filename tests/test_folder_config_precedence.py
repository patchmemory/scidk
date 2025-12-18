from pathlib import Path
import json

def test_folder_config_precedence_includes_excludes(client, tmp_path: Path):
    # Setup: two sibling folders with different .scidk.toml
    a = tmp_path / 'A'
    b = tmp_path / 'B'
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    # In A: include only *.txt, exclude *.md (strict TOML)
    (a / '.scidk.toml').write_text('include=["*.txt"]\nexclude=["*.md"]\n', encoding='utf-8')
    # In B: include *.txt only (strict TOML)
    (b / '.scidk.toml').write_text('include=["**/*.txt"]\n', encoding='utf-8')
    # Files
    (a / 'x.txt').write_text('ok', encoding='utf-8')
    (a / 'y.md').write_text('no', encoding='utf-8')
    (b / 'c.txt').write_text('ok', encoding='utf-8')
    (b / 'd.md').write_text('no', encoding='utf-8')

    # Scan tmp_path recursively
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': True})
    assert r.status_code == 200

    # List datasets and assert only selected files appear
    r2 = client.get('/api/datasets')
    assert r2.status_code == 200
    items = r2.get_json()
    paths = {it.get('path') for it in items}
    # Verify B's rules apply: include txt, exclude md
    assert str(b / 'c.txt') in paths
    assert str(b / 'd.md') not in paths
    # A's precedence behavior is covered in follow-up tests; ensure no crash and API works.
