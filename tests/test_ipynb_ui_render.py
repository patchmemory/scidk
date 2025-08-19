import json
from pathlib import Path


def make_notebook(tmp_path: Path) -> Path:
    nb = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Title\n"]},
            {"cell_type": "code", "source": ["import numpy\n"]},
        ],
        "metadata": {"kernelspec": {"name": "python3", "language": "python"}, "language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    p = tmp_path / 'ui_demo.ipynb'
    p.write_text(json.dumps(nb), encoding='utf-8')
    return p


def test_dataset_detail_renders_notebook_summary(client, tmp_path: Path):
    # Arrange: create notebook file and scan
    nb_path = make_notebook(tmp_path)
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    # Fetch datasets via API to get checksum/id
    ds_resp = client.get('/api/datasets')
    assert ds_resp.status_code == 200
    items = ds_resp.get_json()
    # Find our notebook dataset
    ds = next((d for d in items if d.get('path') == str(nb_path)), None)
    assert ds is not None
    # GET UI detail page
    ui_resp = client.get(f"/datasets/{ds['id']}")
    assert ui_resp.status_code == 200
    html = ui_resp.data.decode('utf-8')
    # Verify Notebook Summary label and kernel/language presence
    assert 'Notebook Summary' in html
    assert 'python3' in html or 'Kernel' in html
