# Parametrization Examples

## Complex Combinations

```python
@pytest.mark.parametrize("threshold", [0.5, 0.8])
@pytest.mark.parametrize("method", ["linear", "cubic"])
def test_interpolation(threshold, method):
    result = interpolate(data, threshold, method)
    assert result is not None
```