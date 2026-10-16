"""Static guard against production runtime NameError regressions.

Python compilation does not catch a global helper that was moved during a refactor
but is still referenced from another module.  This guard uses Python's symbol-table
analysis to verify that every referenced global in production modules resolves to a
module definition/import or a builtin.
"""
from pathlib import Path
import builtins
import symtable

ROOT = Path(__file__).resolve().parent


def production_python_files():
    for path in sorted(ROOT.glob("*.py")):
        if path.name.endswith("_tests.py") or path.name == "release_guard.py":
            continue
        yield path


def unresolved_globals(path: Path) -> set[str]:
    table = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
    module_defs = {
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }
    unresolved: set[str] = set()

    def walk(current):
        for child in current.get_children():
            for symbol in child.get_symbols():
                if symbol.is_referenced() and symbol.is_global():
                    name = symbol.get_name()
                    if name not in module_defs and not hasattr(builtins, name):
                        unresolved.add(name)
            walk(child)

    walk(table)
    return unresolved


def run():
    failures = {}
    checked = 0
    for path in production_python_files():
        checked += 1
        missing = unresolved_globals(path)
        if missing:
            failures[path.name] = sorted(missing)
    if failures:
        lines = [f"{name}: {', '.join(values)}" for name, values in failures.items()]
        raise AssertionError("Unresolved production globals:\n" + "\n".join(lines))
    print(f"runtime_name_guard_tests: PASS ({checked} production modules checked)")


if __name__ == "__main__":
    run()
