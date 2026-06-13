# Property-Based Testing

## Strategy Composition

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers(min_value=0, max_value=100)))
def test_positive_integers(items):
    assert all(x >= 0 for x in items)
```