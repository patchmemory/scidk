from pathlib import Path
from scidk.interpreters.csv_interpreter import CsvInterpreter


def test_csv_interpreter_basic(tmp_path: Path):
    p = tmp_path / 'data.csv'
    p.write_text('a,b,c\n1,2,3\n4,5,6\n', encoding='utf-8')
    interp = CsvInterpreter()
    res = interp.interpret(p)
    assert res['status'] == 'success'
    data = res['data']
    assert data['headers'] == ['a', 'b', 'c']
    assert data['row_count'] == 2
    assert data['delimiter'] == ','


def test_csv_interpreter_large_file_error(tmp_path: Path):
    p = tmp_path / 'big.csv'
    # Create a file larger than 1 KB and set limit small to trigger error
    p.write_text('x\n' * 2048, encoding='utf-8')
    interp = CsvInterpreter(max_bytes=1024)
    res = interp.interpret(p)
    assert res['status'] == 'error'
    assert res['data'].get('error_type') == 'FILE_TOO_LARGE'
