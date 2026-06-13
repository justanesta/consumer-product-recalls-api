# Mocking Patterns

## When to Mock

- External API calls
- Database connections  
- File system operations
- Time-dependent code

## Mock vs MagicMock

```python
from unittest.mock import Mock, MagicMock

# Mock - manual method definition
mock = Mock()
mock.method.return_value = "result"

# MagicMock - auto-defines magic methods
magic = MagicMock()
magic.__len__.return_value = 5
```