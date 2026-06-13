---
name: python-error-handling
description: |
  Python error handling and debugging. Use this skill when implementing error handling, 
  designing exception hierarchies, debugging issues, or adding logging. Covers exception 
  patterns, custom exceptions, logging with structlog, debugging tools, and error recovery.
---

# Python Error Handling

Modern error handling, logging, and debugging patterns.

## Core Principles

1. **Specific exceptions** - Catch specific types, not `Exception`
2. **Fail fast** - Raise errors early at source
3. **Context in errors** - Include relevant information
4. **Log, don't just print** - Structured, searchable logs

## Exception Handling Patterns

**Be specific about what you catch**

```python
# BAD - Too broad
try:
    result = process_data()
except:
    print("Error occurred")

# GOOD - Specific handling
try:
    result = process_data()
except FileNotFoundError as e:
    logger.error(f"Config file not found: {e}")
    use_defaults()
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise
```

See [exception-patterns.md](references/exception-patterns.md).

## Custom Exceptions

**Create domain-specific exceptions**

```python
class DataValidationError(ValueError):
    """Raised when data validation fails."""
    pass

class APIError(Exception):
    """Base exception for API errors."""
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class APITimeout(APIError):
    """API request timeout."""
    def __init__(self, message: str):
        super().__init__(message, status_code=504)
```

See [custom-exceptions.md](references/custom-exceptions.md).

## Context Managers for Cleanup

```python
from contextlib import contextmanager

@contextmanager
def managed_resource(name):
    resource = acquire_resource(name)
    try:
        yield resource
    finally:
        release_resource(resource)  # Always called

with managed_resource("database") as db:
    db.query("SELECT * FROM users")
    # Even if exception, resource released
```

## Logging with Structlog

```python
import structlog

logger = structlog.get_logger()

def process_order(order_id: str):
    log = logger.bind(order_id=order_id)
    
    try:
        log.info("processing_order_started")
        result = process(order_id)
        log.info("processing_order_completed", result=result)
        return result
    except Exception as e:
        log.error("processing_order_failed", error=str(e))
        raise
```

See [logging-patterns.md](references/logging-patterns.md).

## Debugging Tools

**Use pdb for interactive debugging**

```python
def complex_function(data):
    # Set breakpoint
    import pdb; pdb.set_trace()
    
    # Or in Python 3.7+
    breakpoint()
    
    result = process(data)
    return result
```

See [debugging-tools.md](references/debugging-tools.md).

## Error Recovery Patterns

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def unreliable_api_call():
    """Retry with exponential backoff."""
    response = requests.get("https://api.example.com")
    response.raise_for_status()
    return response.json()
```

See [retry-patterns.md](references/retry-patterns.md).

source: Python error handling best practices
