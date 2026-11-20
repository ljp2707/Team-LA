"""Find the text people read in the app's source: the strings, not the code around them.

Used by test_wording.py to make sure "launch" stays out of what users see now that the
app says "program". Variable names, routes, JSON keys and Airtable names are left alone
on purpose, so this only looks at:

- Python: string constants, except docstrings, dict keys, subscripts and log messages.
- TypeScript and TSX: string literals (template literal text too) and JSX text.
  Comments are skipped.

Each finder returns (start, end) character offsets into the source, so a caller can
also rewrite just those spans.
"""

from __future__ import annotations

import ast
import re

# "launch" or "launches" as a whole word. "launched" (the home page verbs) does not match,
# and neither do names joined with a hyphen, such as the CSS class person-launch-head.
LAUNCH_WORD = re.compile(r"(?<![\w-])(launch|launches)(?![\w-])", re.IGNORECASE)

# Phrases that keep the word on purpose. Matched case-insensitively against the text.
ALLOWED = (
    "sites to launch",  # Home page stat, kept by request (the verb, not the noun)
    "nmu-launches",  # Calendar event UIDs and the .ics file name: changing them duplicates events
    "//nmu launches//",  # iCalendar PRODID, never shown
)

_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}


# --- Python -------------------------------------------------------------------------------


def _line_starts(source: str) -> list[int]:
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def python_spans(source: str) -> list[tuple[int, int]]:
    """Spans of user-facing string constants (quotes included) in Python source."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    starts = _line_starts(source)
    skip: set[int] = set()

    for node in ast.walk(tree):
        # Docstrings
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
        # Dict keys ({"launches": rows}) and subscripts (row["launches"]) are data, not text
        elif isinstance(node, ast.Dict):
            skip.update(id(k) for k in node.keys if k is not None)
        elif isinstance(node, ast.Subscript):
            for sub in ast.walk(node.slice):
                skip.add(id(sub))
        # logger.warning("...") is for whoever reads the server log
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_METHODS
        ):
            for arg in node.args:
                for sub in ast.walk(arg):
                    skip.add(id(sub))

    def offset(lineno: int, col: int) -> int:
        # ast columns are UTF-8 byte offsets
        line = lines[lineno - 1]
        return starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", errors="ignore"))

    spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            if node.end_lineno is None or node.end_col_offset is None:
                continue
            spans.append((offset(node.lineno, node.col_offset), offset(node.end_lineno, node.end_col_offset)))
    return sorted(set(spans))


# --- TypeScript and TSX -------------------------------------------------------------------

_JSX_BEFORE = set("(,=?:&|{}>;[!") | {""}


class _Scanner:
    """A small hand-written scanner. Not a full parser: enough for this app's code style."""

    def __init__(self, source: str, jsx: bool):
        self.s = source
        self.n = len(source)
        self.jsx = jsx
        self.spans: list[tuple[int, int]] = []

    def prev_token(self, i: int) -> str:
        j = i - 1
        while j >= 0 and self.s[j].isspace():
            j -= 1
        if j < 0:
            return ""
        if self.s[j].isalnum() or self.s[j] in "_$":
            k = j
            while k >= 0 and (self.s[k].isalnum() or self.s[k] in "_$"):
                k -= 1
            return self.s[k + 1 : j + 1]
        return self.s[j]

    def skip_comment(self, i: int) -> int | None:
        if self.s.startswith("//", i):
            end = self.s.find("\n", i)
            return self.n if end == -1 else end
        if self.s.startswith("/*", i):
            end = self.s.find("*/", i + 2)
            return self.n if end == -1 else end + 2
        return None

    def string(self, i: int) -> int:
        quote = self.s[i]
        j = i + 1
        while j < self.n and self.s[j] != quote:
            j += 2 if self.s[j] == "\\" else 1
        self.spans.append((i, min(j + 1, self.n)))
        return j + 1

    def template(self, i: int) -> int:
        j = i + 1
        start = j
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
            elif c == "`":
                self.spans.append((start, j))
                return j + 1
            elif self.s.startswith("${", j):
                self.spans.append((start, j))
                j = self.code(j + 2, closer="}")
                start = j
            else:
                j += 1
        return j

    def code(self, i: int, closer: str | None = None) -> int:
        """Scan code until the matching closer (or the end). Returns the index after it."""
        depth = 0
        while i < self.n:
            c = self.s[i]
            after_comment = self.skip_comment(i)
            if after_comment is not None:
                i = after_comment
            elif c in "'\"":
                i = self.string(i)
            elif c == "`":
                i = self.template(i)
            elif c in "({[":
                depth += 1
                i += 1
            elif c in ")}]":
                if depth == 0 and closer == c:
                    return i + 1
                depth -= 1
                i += 1
            elif (
                c == "<"
                and self.jsx
                and i + 1 < self.n
                and (self.s[i + 1].isalpha() or self.s[i + 1] == ">")
                and (self.prev_token(i) in _JSX_BEFORE or self.prev_token(i) == "return")
            ):
                i = self.element(i)
            else:
                i += 1
        return i

    def tag(self, i: int) -> tuple[int, bool]:
        """From '<' of an opening tag to just after its '>'. Returns (index, self_closing)."""
        j = i + 1
        angle = 0  # generics such as <Chips<Filter>
        while j < self.n:
            c = self.s[j]
            if c in "'\"":
                j = self.string(j)
            elif c == "{":
                j = self.code(j + 1, closer="}")
            elif c == "<":
                angle += 1
                j += 1
            elif c == ">":
                if angle:
                    angle -= 1
                    j += 1
                    continue
                return j + 1, self.s[j - 1] == "/"
            else:
                j += 1
        return j, True

    def element(self, i: int) -> int:
        """A JSX element: its tag, then its children (text, {code} and nested elements)."""
        i, closed = self.tag(i)
        if closed:
            return i
        depth = 1
        text_start = i
        while i < self.n and depth:
            c = self.s[i]
            if c in "<{":
                if self.s[text_start:i].strip():
                    self.spans.append((text_start, i))
                if c == "{":
                    i = self.code(i + 1, closer="}")
                elif self.s.startswith("</", i):
                    depth -= 1
                    i = self.s.find(">", i) + 1 or self.n
                else:
                    i, closed = self.tag(i)
                    if not closed:
                        depth += 1
                text_start = i
            else:
                i += 1
        return i


def ts_spans(source: str, jsx: bool = True) -> list[tuple[int, int]]:
    """Spans of string literals and JSX text in TypeScript or TSX source."""
    scanner = _Scanner(source, jsx)
    scanner.code(0)
    return sorted(set(scanner.spans))


# --- Checking -----------------------------------------------------------------------------


def launch_words(source: str, spans: list[tuple[int, int]]) -> list[tuple[int, str]]:
    """(line number, text) for each span that says launch or launches outside ALLOWED."""
    found = []
    for start, end in spans:
        text = source[start:end]
        lowered = text.lower()
        for allowed in ALLOWED:
            lowered = lowered.replace(allowed, " " * len(allowed))
        if LAUNCH_WORD.search(lowered):
            found.append((source.count("\n", 0, start) + 1, " ".join(text.split())))
    return found
