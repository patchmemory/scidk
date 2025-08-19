from pathlib import Path
from unittest import mock


def _make_file(tmp_path: Path, name: str = 'a.txt') -> Path:
    f = tmp_path / name
    f.write_text('x', encoding='utf-8')
    return f


def test_scan_source_python_when_no_tools(client, tmp_path: Path):
    _make_file(tmp_path)
    with mock.patch('shutil.which', return_value=None):
        resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
        assert resp.status_code == 200
    d_resp = client.get('/api/directories')
    assert d_resp.status_code == 200
    dirs = d_resp.get_json()
    entry = next(d for d in dirs if d.get('path') == str(tmp_path))
    assert entry.get('source') == 'python'


def test_scan_source_ncdu_preferred_when_output_contains_paths(client, tmp_path: Path):
    f = _make_file(tmp_path, 'b.txt')
    # Simulate ncdu present and returns stdout containing absolute path
    def which(name):
        return '/usr/bin/ncdu' if name == 'ncdu' else None
    fake_stdout = (str(f.resolve()) + "\n").encode('utf-8')
    completed = mock.Mock(stdout=fake_stdout, stderr=b'', returncode=0)
    with mock.patch('shutil.which', side_effect=which):
        with mock.patch('subprocess.run', return_value=completed):
            resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
            assert resp.status_code == 200
    # Directory source should be ncdu
    d_resp = client.get('/api/directories')
    entry = next(d for d in d_resp.get_json() if d.get('path') == str(tmp_path))
    assert entry.get('source') == 'ncdu'


def test_scan_source_gdu_when_ncdu_absent_and_output_contains_paths(client, tmp_path: Path):
    f = _make_file(tmp_path, 'c.txt')
    def which(name):
        if name == 'ncdu':
            return None
        if name == 'gdu':
            return '/usr/bin/gdu'
        return None
    fake_stdout = (str(f.resolve()) + "\n").encode('utf-8')
    completed = mock.Mock(stdout=fake_stdout, stderr=b'', returncode=0)
    with mock.patch('shutil.which', side_effect=which):
        with mock.patch('subprocess.run', return_value=completed):
            resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
            assert resp.status_code == 200
    d_resp = client.get('/api/directories')
    entry = next(d for d in d_resp.get_json() if d.get('path') == str(tmp_path))
    assert entry.get('source') == 'gdu'
