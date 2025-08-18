# SciDK MVP - Run Instructions

This is a minimal runnable MVP to satisfy the current cycle's GUI acceptance: a simple Flask UI that can scan a directory and display datasets with basic Python code interpretation.

## Quick Start

1) Install dependencies (prefer a virtualenv):
```
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

2) Initialize environment variables (recommended):
- bash/zsh:
```
# Export variables for this shell
source scripts/init_env.sh
# Optionally write a .env file for tooling
source scripts/init_env.sh --write-dotenv
```
- fish shell:
```
# Export variables for this shell
source scripts/init_env.fish
# Optionally write a .env file for tooling
source scripts/init_env.fish --write-dotenv
```

3) Run the server:
```
scidk-serve
# or
python -m scidk.app
```

4) Open the UI in your browser:
- http://127.0.0.1:5000/

5) Use the "Scan Files" form to scan a directory (e.g., this repository root). Python files will be interpreted to show imports, functions, and classes.

## Troubleshooting
- Editable install error (Multiple top-level packages discovered): We ship setuptools config to include only the scidk package. If you previously had this error, pull latest and try again: `pip install -e .`.
- Shell errors when initializing env: Use the script matching your shell (`init_env.sh` for bash/zsh, `init_env.fish` for fish). Avoid running `sh scripts/init_env.sh`; instead, source it.

## Neo4j Password: How to Set/Change
- Choose your password before first start by setting NEO4J_AUTH in .env or your shell:
  - echo "NEO4J_AUTH=neo4j/StrongPass123!" >> .env
  - docker compose -f docker-compose.neo4j.yml up -d
- Change an existing password:
  - With container: scripts/neo4j_set_password.sh 'NewPass123!' --container scidk-neo4j --current 'OldPass!'
  - Local cypher-shell: scripts/neo4j_set_password.sh 'NewPass123!' --host bolt://localhost:7687 --user neo4j --current 'OldPass!'
- More details in dev/deployment.md (includes direct cypher-shell commands).

## API
- POST /api/scan {"path": "/path", "recursive": true}
- GET /api/datasets
- GET /api/datasets/<id>

## Testing
We use pytest for unit and API tests.

Run the test suite:
```
# optional: install dev extras to get pytest
pip install -e .[dev]

# run tests
pytest
```

Conventions:
- Tests live in tests/ and rely on pytest fixtures in tests/conftest.py (e.g., Flask app and client).
- Add tests alongside new features in future cycles; see dev/cycles.md for cycle protocol.

## Notes
- This MVP uses an in-memory graph; data resets on restart.
- Neo4j deployment docs reside in dev/deployment.md, but Neo4j is not yet wired in the MVP code.
