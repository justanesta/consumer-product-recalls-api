# Style Guide

## Import Organization

```python
# Standard library
import os
import sys
from pathlib import Path

# Third-party packages
import pandas as pd
import numpy as np
from flask import Flask, request

# Local imports
from mypackage import utils
from mypackage.core import process_data
```

## Naming Conventions

```python
# Variables and functions: snake_case
user_name = "alice"
def calculate_total_price(): pass

# Classes: PascalCase
class UserAccount: pass

# Constants: SCREAMING_SNAKE_CASE
MAX_RETRIES = 3
API_ENDPOINT = "https://api.example.com"

# Private: leading underscore
_internal_variable = 10
def _helper_function(): pass
```

## Line Length and Formatting

```python
# Use black or ruff for automatic formatting

# Long function calls
result = some_function(
    arg1="value1",
    arg2="value2",
    arg3="value3",
)

# Long lists/dicts
data = {
    "key1": "value1",
    "key2": "value2",
    "key3": "value3",
}
```

## Docstrings

```python
def process_data(data: list[dict], threshold: float) -> list[dict]:
    """
    Process data records above threshold.
    
    Args:
        data: List of records to process
        threshold: Minimum value to include
    
    Returns:
        Filtered list of records
    
    Raises:
        ValueError: If data is empty
    """
    pass
```
