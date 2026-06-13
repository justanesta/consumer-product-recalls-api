# Context Manager Examples

## Custom Context Managers

```python
from contextlib import contextmanager
import time

@contextmanager
def timer(name: str):
    """Time a block of code."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"{name}: {elapsed:.3f}s")

with timer("Data processing"):
    process_data()
```

## Class-based Context Managers

```python
class DatabaseConnection:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.connection = None
    
    def __enter__(self):
        self.connection = connect(self.connection_string)
        return self.connection
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.connection.close()
        # Return False to propagate exceptions
        return False

with DatabaseConnection("postgresql://localhost") as conn:
    result = conn.query("SELECT * FROM users")
```

## Async Context Managers

```python
from contextlib import asynccontextmanager
import aiofiles

@asynccontextmanager
async def async_file(path: str):
    """Async file context manager."""
    file = await aiofiles.open(path, 'r')
    try:
        yield file
    finally:
        await file.close()

async with async_file("data.txt") as f:
    content = await f.read()
```

## Error Handling Patterns

```python
@contextmanager
def safe_write(filename):
    """Write to temporary file, rename on success."""
    temp_file = f"{filename}.tmp"
    f = open(temp_file, 'w')
    try:
        yield f
    except Exception:
        f.close()
        Path(temp_file).unlink()  # Delete temp file
        raise
    else:
        f.close()
        Path(temp_file).rename(filename)  # Atomic rename

with safe_write("output.txt") as f:
    f.write("Important data")
    # If exception occurs, temp file is deleted
```
