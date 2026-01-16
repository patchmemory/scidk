import json
import tracemalloc
from pathlib import Path

import pytest

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


def large_notebook_dict(num_cells: int = 1000):
    """Generate a large notebook with many cells for memory testing."""
    cells = []
    for i in range(num_cells):
        if i % 3 == 0:
            cells.append({
                "cell_type": "markdown",
                "source": [f"# Heading {i}\n", f"Description for section {i}\n" * 10]
            })
        elif i % 3 == 1:
            cells.append({
                "cell_type": "code",
                "source": [
                    f"import module{i}\n",
                    f"data_{i} = " + "[" + ", ".join(str(x) for x in range(100)) + "]\n",
                    f"result_{i} = sum(data_{i})\n" * 5
                ]
            })
        else:
            cells.append({
                "cell_type": "raw",
                "source": ["x" * 1000 + "\n"] * 10
            })
    return {
        "cells": cells,
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


@pytest.mark.unit
def test_ipynb_streaming_memory_efficiency_small_notebook(tmp_path: Path):
    """Test that small notebooks are processed with minimal memory overhead."""
    p = tmp_path / 'small.ipynb'
    nb = minimal_notebook_dict()
    p.write_text(json.dumps(nb), encoding='utf-8')

    tracemalloc.start()
    interp = IpynbInterpreter()
    res = interp.interpret(p)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert res['status'] == 'success'
    # Peak memory should be reasonable for a small notebook (< 1MB)
    assert peak < 1024 * 1024, f"Peak memory {peak} bytes exceeds 1MB for small notebook"


@pytest.mark.unit
def test_ipynb_streaming_memory_efficiency_large_notebook(tmp_path: Path):
    """Test that large notebooks benefit from streaming (>=40% memory reduction)."""
    p = tmp_path / 'large.ipynb'
    nb = large_notebook_dict(num_cells=1000)
    content = json.dumps(nb)
    p.write_text(content, encoding='utf-8')
    file_size = p.stat().st_size

    # Measure streaming memory usage
    tracemalloc.start()
    interp = IpynbInterpreter()
    res = interp.interpret(p)
    _, peak_streaming = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert res['status'] == 'success'

    # Measure full-load memory usage for comparison (simulating old behavior)
    tracemalloc.start()
    with open(p, 'r', encoding='utf-8') as f:
        _ = json.load(f)  # Full load into memory
    _, peak_full_load = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Streaming should use significantly less memory than full load
    # Target: >=40% reduction means streaming uses <=60% of full-load memory
    memory_ratio = peak_streaming / peak_full_load
    reduction_pct = (1 - memory_ratio) * 100

    print(f"\nMemory comparison for {file_size:,} byte notebook:")
    print(f"  Full load peak: {peak_full_load:,} bytes")
    print(f"  Streaming peak: {peak_streaming:,} bytes")
    print(f"  Reduction: {reduction_pct:.1f}%")

    assert reduction_pct >= 40.0, (
        f"Streaming memory reduction {reduction_pct:.1f}% is below 40% target. "
        f"Peak streaming: {peak_streaming:,}, Peak full: {peak_full_load:,}"
    )


@pytest.mark.unit
def test_ipynb_streaming_large_notebook_cell_counts(tmp_path: Path):
    """Test that streaming correctly counts cells in large notebooks."""
    p = tmp_path / 'large.ipynb'
    nb = large_notebook_dict(num_cells=1500)
    p.write_text(json.dumps(nb), encoding='utf-8')

    # Increase max_bytes to accommodate large notebook
    interp = IpynbInterpreter(max_bytes=20 * 1024 * 1024)
    res = interp.interpret(p)

    assert res['status'] == 'success'
    data = res['data']
    total_cells = data['cells']['code'] + data['cells']['markdown'] + data['cells']['raw']
    assert total_cells == 1500, f"Expected 1500 cells, got {total_cells}"
    # Each type should have roughly 500 cells (1500 / 3)
    assert 400 <= data['cells']['code'] <= 600
    assert 400 <= data['cells']['markdown'] <= 600
    assert 400 <= data['cells']['raw'] <= 600


@pytest.mark.unit
def test_ipynb_streaming_extracts_imports_and_headings(tmp_path: Path):
    """Test that streaming extracts imports and headings correctly."""
    p = tmp_path / 'large.ipynb'
    nb = large_notebook_dict(num_cells=100)
    p.write_text(json.dumps(nb), encoding='utf-8')

    interp = IpynbInterpreter()
    res = interp.interpret(p)

    assert res['status'] == 'success'
    data = res['data']
    # Should detect some imports from code cells
    assert len(data.get('imports', [])) > 0, "Should detect imports"
    # Should detect some headings from markdown cells
    assert len(data.get('first_headings', [])) > 0, "Should detect headings"
