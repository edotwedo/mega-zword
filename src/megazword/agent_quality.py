"""Conservative static checks for tests edited by the coding loop.

This checks test structure, not correctness. Imported production calls may be
made in helpers or fixtures; locally defined stand-ins do not count.
"""
import ast
import sys


def is_test_path(path):
    return (path.suffix.lower() == ".py" and (
        "tests" in [p.lower() for p in path.parts]
        or path.name.lower().startswith("test_")
        or path.name.lower().endswith("_test.py")))


def check_tests(text, filename):
    try:
        tree = ast.parse(text, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}:{exc.lineno}: invalid Python: {exc.msg}"]
    imports = set()
    raises_names = set()
    pytest_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                if alias.name == "pytest":
                    pytest_names.add(name)
                elif alias.name.split(".")[0] not in sys.stdlib_module_names:
                    imports.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "pytest":
                raises_names.update(a.asname or a.name for a in node.names if a.name == "raises")
            elif (node.module or "").split(".")[0] not in sys.stdlib_module_names:
                imports.update(a.asname or a.name for a in node.names if a.name != "*")

    # Instances constructed from imported production classes retain provenance.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target = node.value.func
            while isinstance(target, ast.Attribute):
                target = target.value
            if isinstance(target, ast.Name) and target.id in imports:
                imports.update(t.id for t in node.targets if isinstance(t, ast.Name))

    functions = {n.name: n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def production_call(function, seen=None):
        seen = set() if seen is None else seen
        if function.name in seen:
            return False
        seen.add(function.name)
        # pytest fixtures are injected via parameters rather than explicit calls.
        for arg in function.args.args + function.args.kwonlyargs:
            if arg.arg in functions and production_call(functions[arg.arg], seen):
                return True
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            target = node.args[1] if raises(node) and len(node.args) >= 2 else node.func
            while isinstance(target, ast.Attribute):
                target = target.value
            if isinstance(target, ast.Name):
                if target.id in imports:
                    return True
                if target.id in functions and production_call(functions[target.id], seen):
                    return True
        return False

    def raises(call):
        return isinstance(call, ast.Call) and (
            isinstance(call.func, ast.Name) and call.func.id in raises_names
            or isinstance(call.func, ast.Attribute) and call.func.attr == "raises"
            and isinstance(call.func.value, ast.Name) and call.func.value.id in pytest_names)

    errors = []
    tests = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("test")]
    for test in tests:
        meaningful = any(
            isinstance(n, ast.Assert) and any(isinstance(x, (ast.Name, ast.Call, ast.Attribute,
                                                           ast.Subscript)) for x in ast.walk(n.test))
            or isinstance(n, ast.With) and any(raises(i.context_expr) for i in n.items)
            or raises(n) and len(n.args) >= 2
            for n in ast.walk(test))
        prefix = f"{filename}:{test.lineno}: {test.name}"
        if not meaningful:
            errors.append(prefix + " has no nonconstant assert or pytest.raises")
        if not production_call(test):
            errors.append(prefix + " calls nothing imported from the module under test (directly or through a helper/fixture)")
    basename = filename.lower().split("/")[-1]
    if not tests and (basename.startswith("test_") or basename.endswith("_test.py")):
        errors.append(f"{filename}: no test functions found")
    return errors
