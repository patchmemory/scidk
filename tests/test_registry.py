from scidk.core.registry import InterpreterRegistry


class DummyInterpreter:
    def __init__(self, id_: str):
        self.id = id_

    def interpret(self, path):
        return {"status": "success", "data": {}}


def test_register_and_select_by_extension():
    reg = InterpreterRegistry()
    py = DummyInterpreter("py")
    txt = DummyInterpreter("txt")
    reg.register_extension(".py", py)
    reg.register_extension(".txt", txt)

    py_list = reg.get_by_extension(".PY")
    assert py in py_list

    selected = reg.select_for_dataset({"extension": ".py"})
    assert selected == [py]


def test_get_by_id():
    reg = InterpreterRegistry()
    interp = DummyInterpreter("foo")
    reg.register_extension(".foo", interp)
    assert reg.get_by_id("foo") is interp
