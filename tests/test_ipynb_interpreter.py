import json
from pathlib import Path

from scidk.interpreters.ipynb_interpreter import IpynbInterpreter


def minimal_notebook_dict():
    return {
        "cells": [
            {"cell_type": "markdown", "source": ["# Introduction\n", "Some text\n", "## Methods\n"]},
            {"cell_type": "code", "source": ["import numpy as np\n", "from pandas import DataFrame\n", "x = 1\n"]},
            {"cell_type": "raw", "source": ["raw stuff\n"]},
        ],
        "metadata": {
            "kernelspec": {"name": "python3", "language": "python"},
            "language_info": {"name": "python"}
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }


def test_ipynb_interpreter_basic(tmp_path: Path):
    p = tmp_path / 'sample.ipynb'
    nb = minimal_notebook_dict()
    p.write_text(json.dumps(nb), encoding='utf-8')
    interp = IpynbInterpreter()
    res = interp.interpret(p)
    assert res['status'] == 'success'
    data = res['data']
    assert data['type'] == 'ipynb'
    assert data['kernel'] == 'python3'
    assert data['language'] == 'python'
    assert data['cells']['code'] == 1
    assert data['cells']['markdown'] == 1
    assert data['cells']['raw'] == 1
    # headings and imports detected
    assert any(h.startswith('#') for h in data.get('first_headings', []))
    assert 'numpy' in data.get('imports', [])
    assert 'pandas' in data.get('imports', [])


def test_ipynb_interpreter_large_file_error(tmp_path: Path):
    p = tmp_path / 'big.ipynb'
    # Create >2KB content and set limit to 1KB to trigger error
    p.write_text('x' * 2048, encoding='utf-8')
    interp = IpynbInterpreter(max_bytes=1024)
    res = interp.interpret(p)
    assert res['status'] == 'error'
    assert res['data'].get('error_type') == 'FILE_TOO_LARGE'
