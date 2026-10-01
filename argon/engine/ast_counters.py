"""Single-pass custom metrics over Rust-backed ast-grep syntax trees."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from ast_grep_py import SgNode

from argon.engine.languages import ParsedSource, parse_source


ASYNC_LISTENER_METHODS = frozenset(
    {"on", "once", "addListener", "addEventListener", "subscribe", "consume", "process", "onSnapshot"}
)
ASYNC_CONSTRUCTORS = frozenset({"WebSocket", "WebSocketServer", "EventSource", "Worker"})
BRANCH_NODE_TYPES = frozenset(
    {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "elif_clause",
        "except_clause",
        "assert_statement",
        "with_statement",
        "ternary_expression",
        "conditional_expression",
        "if_clause",
        "list_comprehension",
        "set_comprehension",
        "dictionary_comprehension",
        "generator_expression",
    }
)
BOOLEAN_OPERATORS = frozenset({"&&", "||", "??", "&&=", "||=", "??=", "and", "or"})
RESOLUTION_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class BranchNode:
    """A counted decision and its one-based source location."""

    node_type: str
    line: int
    operator: str | None = None


@dataclass(frozen=True)
class AstMetrics:
    """Raw per-file metrics collected in one traversal."""

    branches: tuple[BranchNode, ...]
    determinate_outputs: int
    async_boundary_count: int
    relative_specifiers: tuple[str, ...]
    python_async_boundary_count: int
    python_imports: tuple["PythonImport", ...]


@dataclass(frozen=True)
class PythonImport:
    """A relative Python import: dot level, module path, and imported names."""

    level: int
    module: str
    names: tuple[str, ...]


@dataclass
class _MetricsBuilder:
    branches: list[BranchNode]
    outputs: set[str]
    async_receivers: set[str]
    constructor_sites: int
    specifiers: list[str]
    python_async_sites: int
    python_imports: list[PythonImport]


def _text(node: SgNode | None) -> str:
    return "" if node is None else node.text()


def _collapsed(text: str) -> str:
    return SPACE_RUN.sub(" ", text).strip()


def _operator(node: SgNode) -> str:
    for child in node.children():
        if not child.is_named() and child.kind() in BOOLEAN_OPERATORS:
            return child.text()
    return ""


def _branch(node: SgNode, operator: str | None = None) -> BranchNode:
    return BranchNode(node.kind(), node.range().start.line + 1, operator)


def _return_value(node: SgNode) -> str:
    children = node.named_children()
    return "<void>" if not children else _collapsed(children[0].text())


def _arrow_output(node: SgNode) -> str | None:
    body = node.field("body")
    if body is None or body.kind() == "statement_block":
        return None
    return _collapsed(body.text())


def _member_parts(member: SgNode) -> tuple[str, str]:
    return _text(member.field("object")), _text(member.field("property"))


def _listener_receiver(node: SgNode) -> str | None:
    function = node.field("function")
    if function is None or function.kind() != "member_expression":
        return None
    receiver, method = _member_parts(function)
    if method not in ASYNC_LISTENER_METHODS:
        return None
    return _collapsed(receiver)


def _constructor_is_async(node: SgNode) -> bool:
    constructor = node.field("constructor")
    return constructor is not None and constructor.text() in ASYNC_CONSTRUCTORS


def _onmessage_receiver(node: SgNode) -> str | None:
    left = node.field("left")
    if left is None or left.kind() != "member_expression":
        return None
    receiver, property_name = _member_parts(left)
    return _collapsed(receiver) if property_name == "onmessage" else None


def _string_specifier(node: SgNode | None) -> str | None:
    if node is None or node.kind() != "string":
        return None
    text = node.text()
    return text[1:-1] if len(text) >= 2 else None


def _declaration_specifier(node: SgNode) -> str | None:
    return _string_specifier(node.field("source"))


def _python_import(node: SgNode) -> PythonImport | None:
    module_node = node.field("module_name")
    module_text = _text(module_node)
    if not module_text.startswith("."):
        return None
    prefix = len(module_text) - len(module_text.lstrip("."))
    module = module_text[prefix:].replace(".", "/")
    names = []
    for child in node.named_children()[1:]:
        name_node = child.field("name") if child.kind() == "aliased_import" else child
        if name_node is not None and name_node.kind() != "wildcard_import":
            names.append(name_node.text())
    return PythonImport(prefix, module, tuple(names))


def _call_specifier(node: SgNode) -> str | None:
    function = node.field("function")
    is_dynamic_import = function is not None and function.kind() == "import"
    is_require = function is not None and function.kind() == "identifier" and function.text() == "require"
    if not (is_dynamic_import or is_require):
        return None
    arguments = node.field("arguments")
    if arguments is None or not arguments.named_children():
        return None
    return _string_specifier(arguments.named_children()[0])


def _branch_for(node: SgNode) -> BranchNode | None:
    if node.kind() in BRANCH_NODE_TYPES:
        return _branch(node)
    if node.kind() == "case_clause":
        return None if _is_catch_all_case(node) else _branch(node)
    operator = _operator(node)
    return _branch(node, operator) if operator in BOOLEAN_OPERATORS else None


def _is_catch_all_case(node: SgNode) -> bool:
    named = node.named_children()
    if not named:
        return False
    pattern = named[0]
    if pattern.text() == "_":
        return True
    parts = pattern.named_children()
    return (
        len(parts) == 1
        and parts[0].kind() == "dotted_name"
        and "." not in parts[0].text()
    )


def _handle_branch(node: SgNode, metrics: _MetricsBuilder) -> None:
    branch = _branch_for(node)
    if branch is not None:
        metrics.branches.append(branch)


def _handle_return(node: SgNode, metrics: _MetricsBuilder) -> None:
    metrics.outputs.add(_return_value(node))


def _handle_arrow(node: SgNode, metrics: _MetricsBuilder) -> None:
    output = _arrow_output(node)
    if output is not None:
        metrics.outputs.add(output)


def _handle_call(node: SgNode, metrics: _MetricsBuilder) -> None:
    receiver = _listener_receiver(node)
    if receiver is not None:
        metrics.async_receivers.add(receiver)
    specifier = _call_specifier(node)
    if specifier is not None:
        metrics.specifiers.append(specifier)


def _handle_constructor(node: SgNode, metrics: _MetricsBuilder) -> None:
    metrics.constructor_sites += int(_constructor_is_async(node))


def _handle_assignment(node: SgNode, metrics: _MetricsBuilder) -> None:
    receiver = _onmessage_receiver(node)
    if receiver is not None:
        metrics.async_receivers.add(receiver)


def _handle_import(node: SgNode, metrics: _MetricsBuilder) -> None:
    specifier = _declaration_specifier(node)
    if specifier is not None:
        metrics.specifiers.append(specifier)


def _handle_python_import(node: SgNode, metrics: _MetricsBuilder) -> None:
    imported = _python_import(node)
    if imported is not None:
        metrics.python_imports.append(imported)


def _has_async_token(node: SgNode) -> bool:
    return any(not child.is_named() and child.kind() == "async" for child in node.children())


def _handle_python_await(node: SgNode, metrics: _MetricsBuilder) -> None:
    metrics.python_async_sites += int(node.is_named())


def _handle_python_async_loop(node: SgNode, metrics: _MetricsBuilder) -> None:
    metrics.python_async_sites += int(_has_async_token(node))


def _handle_python_async_context(node: SgNode, metrics: _MetricsBuilder) -> None:
    metrics.python_async_sites += int(_has_async_token(node))


_NODE_HANDLERS = {
    **dict.fromkeys(BRANCH_NODE_TYPES, (_handle_branch,)),
    "case_clause": (_handle_branch,),
    "binary_expression": (_handle_branch,),
    "augmented_assignment_expression": (_handle_branch,),
    "boolean_operator": (_handle_branch,),
    "augmented_assignment": (_handle_branch,),
    "for_statement": (_handle_branch, _handle_python_async_loop),
    "with_statement": (_handle_branch, _handle_python_async_context),
    "await": (_handle_python_await,),
    "return_statement": (_handle_return,),
    "arrow_function": (_handle_arrow,),
    "call_expression": (_handle_call,),
    "new_expression": (_handle_constructor,),
    "assignment_expression": (_handle_assignment,),
    "import_statement": (_handle_import,),
    "export_statement": (_handle_import,),
    "import_from_statement": (_handle_python_import,),
}


def analyze_tree(tree: ParsedSource) -> AstMetrics:
    """Collect branches, outputs, async boundaries and import specifiers once."""
    metrics = _MetricsBuilder([], set(), set(), 0, [], 0, [])
    stack = [tree.root]

    while stack:
        node = stack.pop()
        for handler in _NODE_HANDLERS.get(node.kind(), ()):
            handler(node, metrics)
        stack.extend(reversed(node.children()))

    return AstMetrics(
        branches=tuple(metrics.branches),
        determinate_outputs=len(metrics.outputs),
        async_boundary_count=len(metrics.async_receivers) + metrics.constructor_sites,
        relative_specifiers=tuple(metrics.specifiers),
        python_async_boundary_count=metrics.python_async_sites,
        python_imports=tuple(metrics.python_imports),
    )


def find_branch_nodes(tree: ParsedSource) -> list[BranchNode]:
    """Return branches in source order for CLI diagnostics."""
    return list(analyze_tree(tree).branches)


def count_cyclomatic_branches(tree: ParsedSource) -> int:
    """Count decision points; the McCabe base value of one is excluded."""
    return len(analyze_tree(tree).branches)


def count_determinate_outputs(tree: ParsedSource) -> int:
    """Count distinct explicit return and expression-bodied arrow values."""
    return analyze_tree(tree).determinate_outputs


def count_async_boundaries(tree: ParsedSource) -> int:
    """Count JS listener/constructor sites or Python await/async-loop/context sites."""
    metrics = analyze_tree(tree)
    if tree.language == "python":
        return metrics.python_async_boundary_count
    return metrics.async_boundary_count


def _candidate_paths(importer_path: str, specifier: str) -> list[str]:
    base = posixpath.normpath(
        posixpath.join(posixpath.dirname(importer_path.replace("\\", "/")), specifier)
    )
    candidates = [base]
    if base.endswith(".js"):
        stem = base[:-3]
        candidates.extend((stem + ".ts", stem + ".tsx"))
    candidates.extend(base + extension for extension in RESOLUTION_EXTENSIONS)
    candidates.extend(posixpath.join(base, "index" + ext) for ext in RESOLUTION_EXTENSIONS)
    return candidates


def _python_candidates(module_path: str) -> tuple[str, ...]:
    return (posixpath.join(module_path, "__init__.py"), module_path + ".py")


def _first_python_file(module_path: str, file_paths: set[str]) -> str | None:
    return next((path for path in _python_candidates(module_path) if path in file_paths), None)


def _python_package_dir(importer_path: str, level: int, module: str) -> str:
    parts = posixpath.dirname(importer_path.replace("\\", "/")).split("/")
    for _ in range(max(level - 1, 0)):
        if parts:
            parts.pop()
    if module:
        parts.extend(module.split("/"))
    return posixpath.normpath(posixpath.join(*parts)) if parts else "."


def _python_import_targets(
    imported: PythonImport,
    importer_path: str,
    file_paths: set[str],
) -> set[str]:
    package_dir = _python_package_dir(importer_path, imported.level, imported.module)
    package_file = _first_python_file(package_dir, file_paths)
    resolved = {package_file} if package_file is not None else set()
    if not imported.module:
        for name in imported.names:
            child_module = posixpath.join(package_dir, name.replace(".", "/"))
            child_file = _first_python_file(child_module, file_paths)
            if child_file is not None:
                resolved.add(child_file)
    return resolved


def _resolve_python_imports(
    imports: tuple[PythonImport, ...],
    importer_path: str,
    file_paths: set[str],
) -> set[str]:
    resolved = set()
    for imported in imports:
        resolved.update(_python_import_targets(imported, importer_path, file_paths))
    return resolved


def count_relative_imports(
    tree: ParsedSource,
    importer_path: str,
    pr_file_set: set[str],
) -> int:
    """Count distinct reached files using JS paths or Python package resolution."""
    file_paths = {path.replace("\\", "/") for path in pr_file_set}
    metrics = analyze_tree(tree)
    if tree.language == "python":
        return len(_resolve_python_imports(metrics.python_imports, importer_path, file_paths))
    resolved = set()
    for specifier in metrics.relative_specifiers:
        if not specifier.startswith(("./", "../")):
            continue
        for candidate in _candidate_paths(importer_path, specifier):
            if candidate in file_paths:
                resolved.add(candidate)
                break
    return len(resolved)
