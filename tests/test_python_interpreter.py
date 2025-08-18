from scidk.interpreters.python_code import PythonCodeInterpreter


def test_python_interpreter_success(sample_py_file):
    interp = PythonCodeInterpreter()
    res = interp.interpret(sample_py_file)
    assert res["status"] == "success"
    data = res["data"]
    assert "imports" in data and set(["os", "sys", "collections"]).issubset(set(data["imports"]))
    assert "foo" in data["functions"]
    assert "Bar" in data["classes"]
    assert "Example module docstring" in data["docstring"]


def test_python_interpreter_syntax_error(bad_py_file):
    interp = PythonCodeInterpreter()
    res = interp.interpret(bad_py_file)
    assert res["status"] == "error"
    assert res["data"].get("error_type") == "SYNTAX_ERROR"