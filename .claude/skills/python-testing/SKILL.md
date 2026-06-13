---
name: python-testing
description: |
  Modern Python testing with pytest. Use this skill when writing tests, setting up test 
  infrastructure, or debugging test failures. Covers pytest fixtures, parametrization, 
  mocking with unittest.mock, property-based testing with hypothesis, and test organization.
---

# Python Testing

Modern testing patterns with pytest for reliable, maintainable test suites.

## Core Principles

1. **Use pytest over unittest** - Better fixtures, assertions, parametrization
2. **Arrange-Act-Assert pattern** - Clear test structure
3. **Test behavior, not implementation** - Focus on public APIs
4. **Fixtures for setup** - Reusable, composable test state

## Basic Test Structure
````python
def test_process_data_filters_correctly():
    # Arrange
    data = pd.DataFrame({"score": [1, 5, 10]})
    
    # Act
    result = process_data(data, threshold=5)
    
    # Assert
    assert len(result) == 1
    assert result["score"].iloc[0] == 10
````

## Fixtures

**Use fixtures for reusable test setup**
````python
import pytest

@pytest.fixture
def sample_data():
    """Provide sample DataFrame for tests."""
    return pd.DataFrame({
        "id": [1, 2, 3],
        "value": [10, 20, 30]
    })

def test_with_fixture(sample_data):
    result = process_data(sample_data)
    assert len(result) == 3
````

Fixture scopes:
- `scope="function"` (default) - Per test
- `scope="class"` - Per test class
- `scope="module"` - Per file
- `scope="session"` - Once per test run

See [fixture-patterns.md](references/fixture-patterns.md) for:
- Fixture composition
- Parametrized fixtures
- Fixture cleanup (yield pattern)
- conftest.py organization

## Parametrization

**Test multiple inputs efficiently**
````python
@pytest.mark.parametrize("input,expected", [
    (5, 25),
    (0, 0),
    (-3, 9),
])
def test_square(input, expected):
    assert square(input) == expected

# Multiple parameters
@pytest.mark.parametrize("threshold", [0.5, 0.8])
@pytest.mark.parametrize("method", ["linear", "cubic"])
def test_interpolation(threshold, method):
    result = interpolate(data, threshold, method)
    assert result is not None
````

See [parametrization-examples.md](references/parametrization-examples.md) for:
- Complex parameter combinations
- Parametrizing fixtures
- Using pytest.param for IDs
- Indirect parametrization

## Mocking

**Use unittest.mock for external dependencies**
````python
from unittest.mock import Mock, patch, MagicMock

def test_api_call():
    # Mock the requests library
    with patch('mymodule.requests.get') as mock_get:
        mock_get.return_value.json.return_value = {"status": "ok"}
        
        result = fetch_data()
        
        assert result["status"] == "ok"
        mock_get.assert_called_once()

# Mock as fixture
@pytest.fixture
def mock_database():
    with patch('mymodule.Database') as mock_db:
        mock_db.return_value.query.return_value = [{"id": 1}]
        yield mock_db
````

See [mocking-patterns.md](references/mocking-patterns.md) for:
- When to mock vs use real objects
- Mock vs MagicMock
- Side effects and exceptions
- Patching strategies

## Property-Based Testing

**Use hypothesis for generative testing**
````python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_sort_is_idempotent(items):
    """Sorting twice should equal sorting once."""
    assert sorted(sorted(items)) == sorted(items)

@given(st.text(), st.text())
def test_string_concatenation(s1, s2):
    """Concatenation should preserve length."""
    result = s1 + s2
    assert len(result) == len(s1) + len(s2)
````

See [property-based-testing.md](references/property-based-testing.md) for:
- Strategy composition
- Custom strategies
- Stateful testing
- When to use property-based tests

## Test Organization
````
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_processing.py   # Unit tests
│   └── test_validation.py
├── integration/
│   └── test_pipeline.py     # Integration tests
└── fixtures/
    └── sample_data.json     # Test data
````

**conftest.py** for shared fixtures:
````python
import pytest

@pytest.fixture(scope="session")
def test_config():
    return {"api_key": "test", "debug": True}
````

## Assertions
````python
# Basic assertions
assert value == expected
assert value > threshold
assert item in collection

# Approximate comparisons
assert value == pytest.approx(3.14, rel=0.01)

# Exception testing
with pytest.raises(ValueError, match="Invalid input"):
    process_invalid_data()

# Warnings testing
with pytest.warns(DeprecationWarning):
    legacy_function()
````

## Test Markers
````python
@pytest.mark.slow
def test_long_running():
    pass

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    pass

@pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires 3.10+")
def test_pattern_matching():
    pass

# Run with: pytest -m "not slow"
````

## Coverage
````bash
# Run with coverage
pytest --cov=mymodule --cov-report=html

# Enforce coverage threshold
pytest --cov=mymodule --cov-fail-under=80
````

## Anti-Patterns to Avoid

| Avoid | Use Instead |
|-------|-------------|
| `self.assertEqual()` | `assert x == y` |
| Large test classes | Grouped by fixtures |
| Testing implementation details | Test public API behavior |
| No parametrization | `@pytest.mark.parametrize` |
| Manual setup/teardown | Fixtures with yield |

source: pytest documentation, Testing Best Practices