# Fixture Patterns

## Fixture Composition

```python
@pytest.fixture
def database():
    db = Database()
    yield db
    db.close()

@pytest.fixture
def user(database):
    """Fixture using another fixture."""
    user = database.create_user("test")
    return user
```

## Parametrized Fixtures

```python
@pytest.fixture(params=["sqlite", "postgres", "mysql"])
def database(request):
    """Test with multiple database backends."""
    db = connect(request.param)
    yield db
    db.close()
```