"""Rust-backed JavaScript, TypeScript, and Python parsing through ast-grep."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from ast_grep_py import SgNode, SgRoot


LANGUAGES = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".py": "python",
}
SUPPORTED_EXTENSIONS = frozenset(LANGUAGES)


@dataclass(frozen=True)
class ParsedSource:
    """A parsed syntax tree and whether the parser reported an error node."""

    root: SgNode
    has_error: bool
    language: str


def parse_source(filename: str, source: bytes) -> ParsedSource:
    """Parse source bytes with ast-grep's Rust-backed language grammar."""
    extension = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    language = LANGUAGES.get(extension)
    if language is None:
        raise ValueError(f"unsupported source extension: {extension or '<none>'}")
    text = source.decode("utf-8")
    root = SgRoot(text, language).root()
    has_error = root.find(kind="ERROR") is not None
    return ParsedSource(root=root, has_error=has_error, language=language)
