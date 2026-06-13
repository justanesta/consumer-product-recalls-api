---
name: modern-python-patterns
description: |
  Modern Python 3.10+ patterns and idioms. Use this skill when writing new Python code, 
  refactoring legacy code, or enforcing consistent style. Covers type hints, dataclasses, 
  pattern matching, walrus operator, f-strings, pathlib, and context managers.
---

# Modern Python Patterns

Modern Python patterns for 3.10+ emphasizing readability, type safety, and idiomaticity.

## Core Principles

1. **Type hints everywhere** - Function signatures, class attributes, variables when unclear
2. **Dataclasses over dicts** - Structured data with validation
3. **Pathlib over os.path** - Object-oriented file paths
4. **f-strings over .format()** - Readable string formatting

## Type Hints

**Always annotate function signatures**
````python
from typing import Optional, Union
from collections.abc import Sequence

def process_items(
    items: Sequence[str],
    threshold: float = 0.5,
    max_count: Optional[int] = None
) -> list[str]:
    """Process items with optional limit."""
    return [item for item in items if len(item) > threshold]
````

Modern patterns (3.10+):
- Use `list[str]` not `List[str]` (PEP 585)
- Use `str | None` not `Optional[str]` (PEP 604)
- Use `collections.abc` not `typing` for abstract types

See [type-hints-examples.md](references/type-hints-examples.md) for:
- Generic types with TypeVar
- Protocol classes for structural typing
- Literal types and type narrowing
- typing.cast() and type guards

## Dataclasses

**Use dataclasses for structured data**
````python
from dataclasses import dataclass, field

@dataclass
class Config:
    host: str
    port: int = 8080
    debug: bool = False
    tags: list[str] = field(default_factory=list)
````

Benefits:
- Auto-generated `__init__`, `__repr__`, `__eq__`
- Type validation with type hints
- Immutable with `frozen=True`
- Post-init processing with `__post_init__`

See [dataclass-examples.md](references/dataclass-examples.md) for:
- Validation patterns
- Inheritance and composition
- Integration with Pydantic
- Slots for memory optimization

## Pattern Matching (3.10+)

**Use match/case for complex conditionals**
````python
def process_response(response: dict) -> str:
    match response:
        case {"status": "success", "data": data}:
            return f"Success: {data}"
        case {"status": "error", "code": code, "message": msg}:
            return f"Error {code}: {msg}"
        case {"status": status}:
            return f"Unknown status: {status}"
        case _:
            return "Invalid response"
````

See [pattern-matching-examples.md](references/pattern-matching-examples.md) for:
- Sequence patterns
- Class patterns
- Guard clauses
- Structural pattern matching vs if/elif

## Modern File Operations

**Use pathlib instead of os.path**
````python
from pathlib import Path

# Reading files
config_path = Path("config") / "settings.json"
data = config_path.read_text()

# Writing files
output_path = Path("output") / "results.csv"
output_path.write_text(data)

# Iterating
for path in Path("data").glob("*.csv"):
    print(path.stem)  # filename without extension
````

See [pathlib-patterns.md](references/pathlib-patterns.md) for:
- Path manipulation
- File operations
- Glob patterns
- Cross-platform paths

## Context Managers

**Use context managers for resource management**
````python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def timer(name: str) -> Generator[None, None, None]:
    """Context manager for timing operations."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"{name}: {elapsed:.3f}s")

# Usage
with timer("data processing"):
    process_data()
````

See [context-manager-examples.md](references/context-manager-examples.md) for:
- Custom context managers
- contextlib utilities
- Async context managers
- Error handling patterns

## Walrus Operator (3.8+)

**Use := for assignment expressions**
````python
# In conditionals
if (n := len(data)) > 100:
    print(f"Large dataset: {n} items")

# In list comprehensions
[clean for item in items if (clean := item.strip())]

# In while loops
while (line := file.readline()):
    process(line)
````

Use sparingly - improves readability when avoiding duplication.

## F-strings

**Use f-strings for all formatting**
````python
name = "Alice"
score = 95.5

# Basic
message = f"Hello, {name}!"

# Expressions
result = f"Score: {score:.1f}%"

# Multi-line
report = f"""
Name: {name}
Score: {score:.2f}
Status: {'Pass' if score >= 60 else 'Fail'}
"""

# Debug (3.8+)
print(f"{name=}, {score=}")  # name='Alice', score=95.5
````

See [f-string-patterns.md](references/f-string-patterns.md) for:
- Format specifications
- Nested expressions
- Date formatting
- Alignment and padding

## Anti-Patterns to Avoid

| Avoid | Use Instead |
|-------|-------------|
| `os.path.join(a, b)` | `Path(a) / b` |
| `"{}".format(x)` | `f"{x}"` |
| `Optional[str]` (3.10+) | `str \| None` |
| `List[int]` (3.10+) | `list[int]` |
| Complex if/elif chains | `match/case` |
| `dict` for structured data | `dataclass` |

## Style Guidelines

- **Follow PEP 8** - Use tools like ruff or black
- **Type hints on all public APIs** - Internal helpers optional
- **Docstrings for modules, classes, functions** - Use Google or NumPy style
- **Import order**: stdlib, third-party, local (use isort)

See [style-guide.md](references/style-guide.md) for complete conventions.

source: Modern Python best practices