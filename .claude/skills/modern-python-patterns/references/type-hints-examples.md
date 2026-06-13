# Type Hints Examples

## Generic Types with TypeVar

```python
from typing import TypeVar, Callable

T = TypeVar('T')

def first_element(items: list[T]) -> T | None:
    """Return first element or None."""
    return items[0] if items else None

# Usage preserves type
result: str | None = first_element(["a", "b"])  # str | None
number: int | None = first_element([1, 2, 3])   # int | None

# Generic function
def apply_twice(func: Callable[[T], T], value: T) -> T:
    """Apply function twice to value."""
    return func(func(value))

result = apply_twice(lambda x: x * 2, 5)  # Type inferred as int
```

## Protocol Classes for Structural Typing

```python
from typing import Protocol

class Drawable(Protocol):
    """Anything with a draw method."""
    def draw(self) -> None: ...

class Circle:
    def draw(self) -> None:
        print("Drawing circle")

class Square:
    def draw(self) -> None:
        print("Drawing square")

def render(shape: Drawable) -> None:
    """Works with any object that has draw()."""
    shape.draw()

# Both work without explicit inheritance
render(Circle())
render(Square())
```

## Literal Types

```python
from typing import Literal

def set_log_level(level: Literal["debug", "info", "warning", "error"]) -> None:
    """Only accepts specific strings."""
    print(f"Setting level to {level}")

set_log_level("debug")  # OK
set_log_level("trace")  # Type error

# With unions
Status = Literal["pending", "running", "complete", "failed"]

def update_status(task_id: str, status: Status) -> None:
    """Update task status."""
    pass
```

## Type Narrowing with isinstance

```python
def process_value(value: int | str | list) -> str:
    """Process different types appropriately."""
    if isinstance(value, int):
        # Type narrowed to int
        return f"Number: {value * 2}"
    elif isinstance(value, str):
        # Type narrowed to str
        return f"String: {value.upper()}"
    else:
        # Type narrowed to list
        return f"List with {len(value)} items"
```

## Type Guards

```python
from typing import TypeGuard

def is_string_list(items: list) -> TypeGuard[list[str]]:
    """Check if all items are strings."""
    return all(isinstance(item, str) for item in items)

def process_items(items: list[str | int]) -> None:
    if is_string_list(items):
        # Type narrowed to list[str]
        result = " ".join(items)  # OK
    else:
        print("Mixed types")
```

## typing.cast() for Unavoidable Cases

```python
from typing import cast

def get_config() -> dict:
    """Returns config from JSON."""
    return {"host": "localhost", "port": 8080}

# You know the structure but type checker doesn't
config = cast(dict[str, str | int], get_config())
host: str = config["host"]  # Type checker knows this is str
```

## Callable Types

```python
from collections.abc import Callable

# Function that takes int, returns str
def process(func: Callable[[int], str], value: int) -> str:
    return func(value)

# Multiple arguments
def apply(func: Callable[[int, str], bool], num: int, text: str) -> bool:
    return func(num, text)

# Variable arguments
def execute(func: Callable[..., None]) -> None:
    """Function with any arguments returning None."""
    func()
```

## Union and Optional Patterns

```python
# Modern union (3.10+)
def parse_value(raw: str) -> int | float | None:
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return None

# Old style (pre-3.10)
from typing import Union, Optional
def parse_value_old(raw: str) -> Optional[Union[int, float]]:
    pass

# Multiple types
def format_data(data: str | bytes | bytearray) -> str:
    if isinstance(data, str):
        return data
    return data.decode()
```
