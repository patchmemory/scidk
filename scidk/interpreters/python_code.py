import ast
from pathlib import Path


class PythonCodeInterpreter:
    id = "python_code"
    name = "Python Code Analyzer"
    version = "0.1.0"
    extensions = [".py"]

    def interpret(self, file_path: Path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            src = f.read()
        try:
            tree = ast.parse(src)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split('.')[0])
            functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
            return {
                'status': 'success',
                'data': {
                    'imports': sorted(set(imports)),
                    'functions': sorted(set(functions)),
                    'classes': sorted(set(classes)),
                    'docstring': ast.get_docstring(tree) or "",
                }
            }
        except SyntaxError as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'SYNTAX_ERROR',
                    'line': getattr(e, 'lineno', None),
                    'details': str(e),
                }
            }
