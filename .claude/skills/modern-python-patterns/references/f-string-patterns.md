# F-String Patterns

## Format Specifications

```python
# Numbers
value = 123.456
print(f"{value:.2f}")      # 123.46 (2 decimals)
print(f"{value:10.2f}")    # '    123.46' (width 10)
print(f"{value:010.2f}")   # '0000123.46' (zero-padded)

# Percentages
ratio = 0.856
print(f"{ratio:.1%}")      # 85.6%

# Scientific notation
large = 1234567890
print(f"{large:.2e}")      # 1.23e+09
```

## Date Formatting

```python
from datetime import datetime

now = datetime.now()
print(f"{now:%Y-%m-%d}")          # 2024-01-15
print(f"{now:%H:%M:%S}")          # 14:30:45
print(f"{now:%B %d, %Y}")         # January 15, 2024
```

## Alignment and Padding

```python
# Left, center, right alignment
text = "hello"
print(f"{text:<10}")   # 'hello     '
print(f"{text:^10}")   # '  hello   '
print(f"{text:>10}")   # '     hello'

# With fill character
print(f"{text:*^10}")  # '**hello***'
```

## Nested Expressions

```python
data = {"name": "Alice", "age": 30}
print(f"{data['name'].upper()} is {data['age']} years old")

# Conditional expressions
status = "active"
print(f"Status: {status.upper() if status == 'active' else 'INACTIVE'}")
```
