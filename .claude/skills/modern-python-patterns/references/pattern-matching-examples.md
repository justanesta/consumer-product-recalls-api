# Pattern Matching Examples

## Sequence Patterns

```python
def process_coordinates(point: tuple) -> str:
    match point:
        case (0, 0):
            return "Origin"
        case (0, y):
            return f"Y-axis at {y}"
        case (x, 0):
            return f"X-axis at {x}"
        case (x, y):
            return f"Point at ({x}, {y})"
```

## Class Patterns

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

@dataclass
class Circle:
    center: Point
    radius: float

def describe_shape(shape):
    match shape:
        case Circle(center=Point(x=0, y=0), radius=r):
            return f"Circle at origin with radius {r}"
        case Circle(center=Point(x=x, y=y), radius=r):
            return f"Circle at ({x}, {y}) with radius {r}"
        case Point(x=x, y=y):
            return f"Point at ({x}, {y})"
```

## Guard Clauses

```python
def categorize_number(x: int) -> str:
    match x:
        case n if n < 0:
            return "negative"
        case 0:
            return "zero"
        case n if n < 10:
            return "single digit"
        case n if n < 100:
            return "double digit"
        case _:
            return "large number"
```

## Matching vs If/Elif

```python
# Traditional if/elif
def process_response_old(response):
    if response.get("status") == "success" and "data" in response:
        return f"Success: {response['data']}"
    elif response.get("status") == "error":
        return f"Error: {response.get('message', 'Unknown')}"
    else:
        return "Unknown response"

# Pattern matching (clearer)
def process_response_new(response):
    match response:
        case {"status": "success", "data": data}:
            return f"Success: {data}"
        case {"status": "error", "message": msg}:
            return f"Error: {msg}"
        case {"status": "error"}:
            return "Error: Unknown"
        case _:
            return "Unknown response"
```
