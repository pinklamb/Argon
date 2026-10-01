from pathlib import Path

from argon.engine.ast_counters import (
    analyze_tree,
    count_async_boundaries,
    count_cyclomatic_branches,
    count_determinate_outputs,
    count_relative_imports,
    parse_source,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_branches():
    tree = parse_source("branches.js", (FIXTURES / "branches.js").read_bytes())

    assert count_cyclomatic_branches(tree) == 5


def test_outputs():
    tree = parse_source("branches.js", (FIXTURES / "branches.js").read_bytes())

    assert count_determinate_outputs(tree) == 3


def test_async_dedupe():
    source = b'''\
socket.on("message", a);
socket.on("close", b);
queue.on("job", c);
bus.subscribe(d);
'''
    tree = parse_source("async.js", source)

    assert count_async_boundaries(tree) == 3


def test_async_new():
    tree = parse_source("async.js", b'new WebSocket(url); new Worker("worker.js");')

    assert count_async_boundaries(tree) == 2


def test_onmessage():
    source = b"socket.onmessage = a; socket.onmessage = b; worker.onmessage = c;"
    tree = parse_source("async.js", source)

    assert count_async_boundaries(tree) == 2


def test_import_ext():
    tree = parse_source("src/a.ts", b'import "./b";')

    assert count_relative_imports(tree, "src/a.ts", {"src/b.ts"}) == 1


def test_import_dedupe():
    tree = parse_source("src/a.ts", b'import "./b"; import "./b.js";')

    assert count_relative_imports(tree, "src/a.ts", {"src/b.ts"}) == 1


def test_package():
    tree = parse_source("src/a.ts", b'import "react";')

    assert count_relative_imports(tree, "src/a.ts", {"src/react.ts"}) == 0


def test_dynamic_template():
    tree = parse_source("src/a.ts", b'import(`./${moduleName}`);')

    assert count_relative_imports(tree, "src/a.ts", {"src/moduleName.ts"}) == 0


def test_empty_require():
    tree = parse_source("src/a.ts", b"require();")

    assert count_relative_imports(tree, "src/a.ts", {"src/moduleName.ts"}) == 0


def test_all_metrics():
    tree = parse_source("branches.js", (FIXTURES / "branches.js").read_bytes())

    metrics = analyze_tree(tree)

    assert len(metrics.branches) == 5
    assert metrics.determinate_outputs == 3


def test_tsx():
    tree = parse_source("component.tsx", b"const view = <div />;")

    assert not tree.has_error


def test_python_branches():
    source = b'''\
def grade(value):
    if value > 0 and value < 10:
        return 1
    elif value < 0:
        return 0
    for item in range(value):
        pass
    while value:
        value -= 1
    try:
        pass
    except ValueError:
        pass
    return 1 if value else 0
'''
    tree = parse_source("grade.py", source)

    assert not tree.has_error
    assert count_cyclomatic_branches(tree) == 7


def test_python_match_cases():
    source = b'''\
def choose(value):
    match value:
        case 1:
            return "one"
        case 2 | 3:
            return "small"
        case name:
            return name
'''
    tree = parse_source("match.py", source)

    assert not tree.has_error
    assert count_cyclomatic_branches(tree) == 2


def test_python_comprehension_branches():
    source = b"def select(values):\n    return [x for x in values if x and x > 0 if x < 10]\n"
    tree = parse_source("comprehension.py", source)

    assert count_cyclomatic_branches(tree) == 4


def test_python_assert_and_with():
    source = b"def check(stream, value):\n    with stream:\n        assert value\n"
    tree = parse_source("assert_with.py", source)

    assert count_cyclomatic_branches(tree) == 2


def test_python_async_suspensions():
    source = b'''\
async def read_all(source):
    await source.open()
    await source.read()
    async for item in source:
        await item.process()
    async with source:
        pass
'''
    tree = parse_source("async_source.py", source)

    assert not tree.has_error
    assert count_async_boundaries(tree) == 5


def test_python_relative_imports():
    source = b'''\
from . import sibling
from ..utils import parse
from ..utils import parse as parse_again
from typing import Any
'''
    tree = parse_source("src/pkg/sub/module.py", source)
    pr_files = {
        "src/pkg/sub/module.py",
        "src/pkg/sub/__init__.py",
        "src/pkg/sub/sibling.py",
        "src/pkg/utils.py",
        "src/pkg/__init__.py",
    }

    assert count_relative_imports(tree, "src/pkg/sub/module.py", pr_files) == 3


def test_broken():
    tree = parse_source("broken.js", b"function broken( {")

    assert tree.has_error
