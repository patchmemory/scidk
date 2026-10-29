"""Authenticated development activation without invoking production services."""
import pytest
from flask import Flask

from scidk.core.auth import AuthManager
from scidk.dev_gui import build_app
from scidk.dev_system_demo import configure


def test_development_startup_requires_auth_and_refuses_inherited_graphs(tmp_path, monkeypatch):
    for name in ('NEO4J_URI', 'BOLT_URI', 'CHAT_NEO4J_URI', 'SCIDK_CONCEPT_NEO4J_URI',
                 'NEO4J_AUTH', 'CHAT_NEO4J_AUTH', 'SCIDK_CONCEPT_NEO4J_AUTH'):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match='administrator'):
        build_app(tmp_path)
    auth = AuthManager(str(tmp_path / 'scidk_settings.db'))
    auth.create_user('dev-admin', 'synthetic-password', role='admin'); auth.close()
    monkeypatch.setenv('NEO4J_URI', 'synthetic-inherited-address')
    with pytest.raises(ValueError, match='clean development environment'):
        build_app(tmp_path)
    monkeypatch.delenv('NEO4J_URI')
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    import scidk.app
    monkeypatch.setattr(scidk.app, 'create_app', lambda: Flask(__name__))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SCIDK_SETTINGS_DB', '')
    monkeypatch.setenv('SCIDK_DB_PATH', '')
    monkeypatch.setenv('SCIDK_DISABLE_SCHEDULER', '')
    monkeypatch.setenv('SCIDK_CONCEPT_GRAPH_ENABLED', '')
    monkeypatch.setenv('SCIDK_GRAPH_BACKEND', '')
    monkeypatch.setenv('SCIDK_SCAN_DB_DIR', '')
    monkeypatch.setenv('SCIDK_ROCRATE_DIR', '')
    app = build_app(tmp_path, configure='scidk.dev_system_demo:configure')
    import os
    assert os.environ['SCIDK_SCAN_DB_DIR'] == str(tmp_path / 'scans')
    assert os.environ['SCIDK_ROCRATE_DIR'] == str(tmp_path / 'crates')
    assert os.environ['SCIDK_DISABLE_SCHEDULER'] == '1'
    assert app.config['SCIDK_GUI_V3_ENABLED'] is True and app.config['SCIDK_REVIEW_CHAT_ENABLED'] is True
    assert app.extensions['knowledge_services'].system.projection.snapshot()['metadata']['synthetic'] is True
    assert app.extensions['knowledge_services'].assertions is None
    # The synthetic hook creates neither review decisions nor graph connections.
    assert 'curation_review' not in app.extensions and 'agent_neo4j' not in app.extensions
