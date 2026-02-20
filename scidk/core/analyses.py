"""
Core analyses module for running analytical scripts on the knowledge graph.

Supports:
- Script registry (built-in and custom scripts)
- Script execution (Cypher, Python)
- Results storage and export
- Jupyter notebook generation
"""
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import path_index_sqlite as pix


class AnalysisScript:
    """Represents an analysis script with metadata and execution logic."""

    def __init__(
        self,
        id: str,
        name: str,
        language: str,
        category: str,
        code: str,
        description: str = "",
        parameters: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
        created_at: Optional[float] = None,
        created_by: Optional[str] = None,
        updated_at: Optional[float] = None
    ):
        self.id = id
        self.name = name
        self.language = language  # cypher, python
        self.category = category  # builtin, custom
        self.code = code
        self.description = description
        self.parameters = parameters or []
        self.tags = tags or []
        self.created_at = created_at or time.time()
        self.created_by = created_by
        self.updated_at = updated_at or time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'language': self.language,
            'category': self.category,
            'code': self.code,
            'description': self.description,
            'parameters': self.parameters,
            'tags': self.tags,
            'created_at': self.created_at,
            'created_by': self.created_by,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnalysisScript':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            name=data['name'],
            language=data['language'],
            category=data['category'],
            code=data['code'],
            description=data.get('description', ''),
            parameters=data.get('parameters', []),
            tags=data.get('tags', []),
            created_at=data.get('created_at'),
            created_by=data.get('created_by'),
            updated_at=data.get('updated_at')
        )


class AnalysisResult:
    """Represents the result of executing an analysis script."""

    def __init__(
        self,
        id: str,
        script_id: str,
        executed_at: float,
        status: str,
        executed_by: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        execution_time_ms: Optional[int] = None,
        error: Optional[str] = None
    ):
        self.id = id
        self.script_id = script_id
        self.executed_at = executed_at
        self.status = status  # success, error
        self.executed_by = executed_by
        self.parameters = parameters or {}
        self.results = results or []
        self.execution_time_ms = execution_time_ms
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'script_id': self.script_id,
            'executed_at': self.executed_at,
            'status': self.status,
            'executed_by': self.executed_by,
            'parameters': self.parameters,
            'results': self.results,
            'execution_time_ms': self.execution_time_ms,
            'error': self.error
        }


class AnalysesManager:
    """Manages analysis scripts and execution."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        """Initialize with optional database connection."""
        self.conn = conn
        self._own_conn = False
        if self.conn is None:
            self.conn = pix.connect()
            self._own_conn = True

    def __del__(self):
        """Close connection if we own it."""
        if self._own_conn and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

    # Script CRUD operations

    def create_script(self, script: AnalysisScript) -> AnalysisScript:
        """Save a new analysis script to the database."""
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO analyses_scripts
            (id, name, description, language, category, code, parameters, tags, created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                script.id,
                script.name,
                script.description,
                script.language,
                script.category,
                script.code,
                json.dumps(script.parameters),
                json.dumps(script.tags),
                script.created_at,
                script.created_by,
                script.updated_at
            )
        )
        self.conn.commit()
        return script

    def get_script(self, script_id: str) -> Optional[AnalysisScript]:
        """Retrieve a script by ID."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT * FROM analyses_scripts WHERE id = ?",
            (script_id,)
        ).fetchone()

        if not row:
            return None

        return self._row_to_script(row)

    def list_scripts(
        self,
        category: Optional[str] = None,
        language: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> List[AnalysisScript]:
        """List all scripts with optional filters."""
        cur = self.conn.cursor()

        query = "SELECT * FROM analyses_scripts WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if language:
            query += " AND language = ?"
            params.append(language)
        if created_by:
            query += " AND created_by = ?"
            params.append(created_by)

        query += " ORDER BY category, name"

        rows = cur.execute(query, params).fetchall()
        return [self._row_to_script(row) for row in rows]

    def update_script(self, script: AnalysisScript) -> AnalysisScript:
        """Update an existing script."""
        script.updated_at = time.time()
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE analyses_scripts
            SET name = ?, description = ?, language = ?, category = ?,
                code = ?, parameters = ?, tags = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                script.name,
                script.description,
                script.language,
                script.category,
                script.code,
                json.dumps(script.parameters),
                json.dumps(script.tags),
                script.updated_at,
                script.id
            )
        )
        self.conn.commit()
        return script

    def delete_script(self, script_id: str) -> bool:
        """Delete a script and its results."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM analyses_scripts WHERE id = ?", (script_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # Result operations

    def save_result(self, result: AnalysisResult) -> AnalysisResult:
        """Save an execution result."""
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO analyses_results
            (id, script_id, executed_at, executed_by, parameters, results, execution_time_ms, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.script_id,
                result.executed_at,
                result.executed_by,
                json.dumps(result.parameters),
                json.dumps(result.results),
                result.execution_time_ms,
                result.status,
                result.error
            )
        )
        self.conn.commit()
        return result

    def get_result(self, result_id: str) -> Optional[AnalysisResult]:
        """Retrieve a result by ID."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT * FROM analyses_results WHERE id = ?",
            (result_id,)
        ).fetchone()

        if not row:
            return None

        return self._row_to_result(row)

    def list_results(
        self,
        script_id: Optional[str] = None,
        executed_by: Optional[str] = None,
        limit: int = 50
    ) -> List[AnalysisResult]:
        """List execution results with optional filters."""
        cur = self.conn.cursor()

        query = "SELECT * FROM analyses_results WHERE 1=1"
        params = []

        if script_id:
            query += " AND script_id = ?"
            params.append(script_id)
        if executed_by:
            query += " AND executed_by = ?"
            params.append(executed_by)

        query += " ORDER BY executed_at DESC LIMIT ?"
        params.append(limit)

        rows = cur.execute(query, params).fetchall()
        return [self._row_to_result(row) for row in rows]

    def delete_result(self, result_id: str) -> bool:
        """Delete a result."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM analyses_results WHERE id = ?", (result_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # Script execution

    def execute_script(
        self,
        script_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        neo4j_driver=None,
        executed_by: Optional[str] = None
    ) -> AnalysisResult:
        """Execute an analysis script and return the result."""
        script = self.get_script(script_id)
        if not script:
            raise ValueError(f"Script not found: {script_id}")

        start_time = time.time()
        result_id = str(uuid.uuid4())
        parameters = parameters or {}

        try:
            # Execute based on language
            if script.language == 'cypher':
                results = self._execute_cypher(script, parameters, neo4j_driver)
            elif script.language == 'python':
                results = self._execute_python(script, parameters, neo4j_driver)
            else:
                raise ValueError(f"Unsupported language: {script.language}")

            execution_time_ms = int((time.time() - start_time) * 1000)

            result = AnalysisResult(
                id=result_id,
                script_id=script_id,
                executed_at=time.time(),
                status='success',
                executed_by=executed_by,
                parameters=parameters,
                results=results,
                execution_time_ms=execution_time_ms
            )
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            result = AnalysisResult(
                id=result_id,
                script_id=script_id,
                executed_at=time.time(),
                status='error',
                executed_by=executed_by,
                parameters=parameters,
                execution_time_ms=execution_time_ms,
                error=str(e)
            )

        # Save result to database
        self.save_result(result)
        return result

    def _execute_cypher(
        self,
        script: AnalysisScript,
        parameters: Dict[str, Any],
        neo4j_driver
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query."""
        if not neo4j_driver:
            raise ValueError("Neo4j driver required for Cypher execution")

        with neo4j_driver.session() as session:
            result = session.run(script.code, parameters)
            return [dict(record) for record in result]

    def _execute_python(
        self,
        script: AnalysisScript,
        parameters: Dict[str, Any],
        neo4j_driver
    ) -> List[Dict[str, Any]]:
        """Execute a Python script."""
        # Prepare safe execution environment
        import pandas as pd

        # Global namespace for script execution
        global_namespace = {
            'parameters': parameters,
            'neo4j_driver': neo4j_driver,
            'pd': pd,
            'json': json,
            'results': []  # Script should populate this
        }

        # Execute script
        exec(script.code, global_namespace)

        # Extract results
        results = global_namespace.get('results', [])

        # Convert pandas DataFrame to list of dicts if needed
        if isinstance(results, pd.DataFrame):
            results = results.to_dict('records')

        return results

    # Helper methods

    def _row_to_script(self, row: Tuple) -> AnalysisScript:
        """Convert database row to AnalysisScript."""
        return AnalysisScript(
            id=row[0],
            name=row[1],
            description=row[2] or '',
            language=row[3],
            category=row[4],
            code=row[5],
            parameters=json.loads(row[6]) if row[6] else [],
            tags=json.loads(row[7]) if row[7] else [],
            created_at=row[8],
            created_by=row[9],
            updated_at=row[10]
        )

    def _row_to_result(self, row: Tuple) -> AnalysisResult:
        """Convert database row to AnalysisResult."""
        return AnalysisResult(
            id=row[0],
            script_id=row[1],
            executed_at=row[2],
            executed_by=row[3],
            parameters=json.loads(row[4]) if row[4] else {},
            results=json.loads(row[5]) if row[5] else [],
            execution_time_ms=row[6],
            status=row[7],
            error=row[8]
        )


# Export functions

def export_to_csv(results: List[Dict[str, Any]]) -> str:
    """Export results to CSV format."""
    import csv
    import io

    if not results:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)
    return output.getvalue()


def export_to_json(results: List[Dict[str, Any]]) -> str:
    """Export results to JSON format."""
    return json.dumps(results, indent=2)


def export_to_jupyter(
    script: AnalysisScript,
    result: Optional[AnalysisResult] = None,
    neo4j_config: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Generate a Jupyter notebook (.ipynb) with the script and optionally results."""
    cells = []

    # Cell 1: Setup and imports
    setup_code = """# Analysis Script: {name}
# Generated by SciDK Analysis Page

import json
""".format(name=script.name)

    if script.language == 'cypher' or neo4j_config:
        setup_code += """
from neo4j import GraphDatabase
import pandas as pd

# Neo4j connection
driver = GraphDatabase.driver(
    "{uri}",
    auth=("{user}", "{password}")
)
""".format(
            uri=neo4j_config.get('uri', 'bolt://localhost:7687') if neo4j_config else 'bolt://localhost:7687',
            user=neo4j_config.get('user', 'neo4j') if neo4j_config else 'neo4j',
            password=neo4j_config.get('password', 'password') if neo4j_config else 'password'
        )

    cells.append({
        'cell_type': 'markdown',
        'metadata': {},
        'source': [f'# {script.name}\n\n{script.description}']
    })

    cells.append({
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [],
        'source': [setup_code]
    })

    # Cell 2: The actual script
    if script.language == 'cypher':
        script_code = """
# Execute Cypher query
query = \"\"\"
{code}
\"\"\"

with driver.session() as session:
    result = session.run(query)
    df = pd.DataFrame([dict(record) for record in result])

df
""".format(code=script.code)
    else:  # python
        script_code = script.code

    cells.append({
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [],
        'source': [script_code]
    })

    # Cell 3: Results if available
    if result and result.results:
        results_code = """
# Results from execution on {executed_at}
results_data = {results}
df = pd.DataFrame(results_data)
df
""".format(
            executed_at=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result.executed_at)),
            results=json.dumps(result.results)
        )

        cells.append({
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': [results_code]
        })

    # Cell 4: Cleanup
    cleanup_code = """
# Close connection
driver.close()
"""
    if script.language == 'cypher' or neo4j_config:
        cells.append({
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': [cleanup_code]
        })

    # Build notebook structure
    notebook = {
        'cells': cells,
        'metadata': {
            'kernelspec': {
                'display_name': 'Python 3',
                'language': 'python',
                'name': 'python3'
            },
            'language_info': {
                'name': 'python',
                'version': '3.9.0'
            }
        },
        'nbformat': 4,
        'nbformat_minor': 4
    }

    return notebook


def import_from_jupyter(notebook_path: Path) -> List[AnalysisScript]:
    """Extract analysis scripts from a Jupyter notebook."""
    with open(notebook_path, 'r') as f:
        notebook = json.load(f)

    scripts = []
    cells = notebook.get('cells', [])

    for idx, cell in enumerate(cells):
        if cell.get('cell_type') != 'code':
            continue

        source = ''.join(cell.get('source', []))

        # Try to detect Cypher queries
        if 'MATCH' in source or 'CREATE' in source or 'MERGE' in source:
            # Extract Cypher from source
            script_id = f"imported-{notebook_path.stem}-{idx}"
            name = f"Imported: {notebook_path.stem} Cell {idx}"

            scripts.append(AnalysisScript(
                id=script_id,
                name=name,
                language='cypher',
                category='custom',
                code=source,
                description=f"Imported from {notebook_path.name}",
                tags=['imported', 'jupyter']
            ))
        elif source.strip():
            # Python script
            script_id = f"imported-{notebook_path.stem}-{idx}"
            name = f"Imported: {notebook_path.stem} Cell {idx}"

            scripts.append(AnalysisScript(
                id=script_id,
                name=name,
                language='python',
                category='custom',
                code=source,
                description=f"Imported from {notebook_path.name}",
                tags=['imported', 'jupyter']
            ))

    return scripts
