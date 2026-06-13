# Testing Data Pipelines

## Unit Testing Tasks

```python
import pytest
from unittest.mock import Mock, patch

def test_extract_data():
    """Test data extraction logic."""
    with patch('module.fetch_from_api') as mock_fetch:
        mock_fetch.return_value = [{"id": 1, "value": 100}]
        
        result = extract_data("test_source")
        
        assert len(result) == 1
        assert result[0]["id"] == 1
        mock_fetch.assert_called_once_with("test_source")

def test_transform_data():
    """Test transformation logic."""
    input_data = [{"id": 1, "value": 100}]
    
    result = transform_data(input_data)
    
    assert "transformed_value" in result[0]
    assert result[0]["transformed_value"] == 200
```

## Integration Testing Flows

```python
@pytest.fixture
def mock_database():
    """Mock database for testing."""
    db = Mock()
    db.query.return_value = [{"id": 1}]
    return db

def test_etl_pipeline_integration(mock_database):
    """Test entire pipeline with mocked dependencies."""
    with patch('module.database', mock_database):
        result = etl_pipeline("test_source", "test_dest")
        
        # Verify pipeline completed
        assert result is not None
        
        # Verify database interactions
        assert mock_database.insert.called
```

## Testing with Test Data

```python
@pytest.fixture
def sample_data():
    """Provide sample data for testing."""
    return [
        {"id": 1, "name": "Alice", "amount": 100},
        {"id": 2, "name": "Bob", "amount": 200}
    ]

def test_transform_with_sample_data(sample_data):
    """Test with realistic sample data."""
    result = transform_data(sample_data)
    
    assert len(result) == 2
    assert all("processed" in r for r in result)
```

## Testing Idempotency

```python
def test_pipeline_idempotency():
    """Test that running twice produces same result."""
    # Run pipeline first time
    result1 = pipeline.run()
    
    # Run pipeline second time
    result2 = pipeline.run()
    
    # Results should be identical
    assert result1 == result2
```

## Testing Error Handling

```python
def test_pipeline_handles_empty_data():
    """Test pipeline handles empty data gracefully."""
    with patch('module.extract_data', return_value=[]):
        with pytest.raises(ValueError, match="No data to process"):
            etl_pipeline("source", "dest")

def test_pipeline_handles_api_failure():
    """Test pipeline handles API failures."""
    with patch('module.fetch_from_api', side_effect=ConnectionError):
        result = extract_data("source")
        assert result == []  # Returns empty on error
```

## Local Development Setup

```python
# conftest.py - Shared test fixtures
import pytest

@pytest.fixture
def test_config():
    """Test configuration."""
    return {
        "database": "test_db",
        "api_endpoint": "http://localhost:8000",
        "debug": True
    }

@pytest.fixture(scope="session")
def test_database():
    """Setup test database."""
    db = create_test_database()
    yield db
    cleanup_test_database(db)
```

## Performance Testing

```python
import time

def test_pipeline_performance():
    """Test pipeline completes within time limit."""
    start = time.time()
    
    result = etl_pipeline("source", "dest")
    
    duration = time.time() - start
    assert duration < 300, f"Pipeline took {duration}s (limit: 300s)"
```
