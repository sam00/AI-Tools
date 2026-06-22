"""Code compressor.

Agents frequently read whole files when they only need the *shape* of the code:
imports, class/function signatures, and docstrings. This compressor extracts that
skeleton and elides function bodies (recoverable via CCR).

- Python is handled precisely with the standard-library ``ast`` module.
- Other languages use a brace/indent-aware signature extractor that keeps
  declarations and the first line of each block while collapsing deep bodies.
"""

from __future__ import annotations

import ast
import re

from ..config import Config

_DECL_RE = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*"
    r"(?:def |class |interface |struct |enum |func |function |fn |impl |trait |"
    r"type |const |let |var |import |from |#include|package |namespace )"
)
_COMMENT_RE = re.compile(r"^\s*(?://|#|/\*|\*)")


def _python_skeleton(source: str, keep: float) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _generic_skeleton(source, keep)

    lines = source.splitlines()
    out: list[str] = []

    def emit_node(node: ast.AST, indent: str = "") -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.append(indent + ast.get_source_segment(source, node).strip())
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            header_line = lines[node.lineno - 1].rstrip()
            out.append(header_line)
            doc = ast.get_docstring(node)
            body_indent = " " * (len(header_line) - len(header_line.lstrip()) + 4)
            if doc:
                first = doc.strip().splitlines()[0]
                out.append(f'{body_indent}"""{first}"""')
            if isinstance(node, ast.ClassDef):
                # Recurse to keep method signatures.
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        emit_node(child, body_indent)
                out.append(f"{body_indent}# … {_count_methods(node)} methods")
            else:
                out.append(f"{body_indent}...  # body elided")
            return
        if isinstance(node, ast.Assign):
            seg = ast.get_source_segment(source, node)
            if seg and len(seg) < 200:
                out.append(seg.strip())

    for node in tree.body:
        emit_node(node)

    skeleton = "\n".join(out)
    return skeleton if skeleton.strip() else source


def _count_methods(node: ast.ClassDef) -> int:
    return sum(1 for c in node.body if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)))


def _generic_skeleton(source: str, keep: float) -> str:
    lines = source.splitlines()
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        stripped = ln.strip()
        is_decl = bool(_DECL_RE.match(ln))
        is_doc_comment = bool(_COMMENT_RE.match(ln))
        is_brace = stripped in {"}", "};", ")", "});"}
        indent = len(ln) - len(ln.lstrip())
        # Keep declarations, shallow lines, closing braces, and doc comments.
        if is_decl or is_brace or (indent <= 4 and stripped) or is_doc_comment:
            out.append(ln)
            prev_blank = False
        elif not prev_blank:
            out.append(" " * (indent) + "// …")
            prev_blank = True
    skeleton = "\n".join(out)
    return skeleton if len(skeleton) < len(source) else source


class CodeCompressor:
    kind = "code"

    def compress(self, text: str, config: Config) -> str:
        # Cheap Python detection: presence of python-only keywords + indentation.
        looks_python = bool(re.search(r"(?m)^\s*(def |class |import |from \w+ import |async def )", text))
        has_braces = text.count("{") + text.count("}") > 4
        if looks_python and not has_braces:
            result = _python_skeleton(text, config.keep_ratio)
        else:
            result = _generic_skeleton(text, config.keep_ratio)
        if len(result) >= len(text):
            return text
        return result
