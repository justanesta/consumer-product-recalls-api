# Pipeline Design Patterns

## Idempotency

**Pipelines should produce same result when run multiple times**

```python
# BAD - Appends each run
def load_data(data):
    db.insert(data)  # Duplicates if rerun!

# GOOD - Upsert based on key
def load_data(data):
    for record in data:
        db.upsert(record, key='id')

# GOOD - Delete and reload
def load_data(data, date):
    db.delete(date=date)
    db.insert(data)
```

## Incremental Processing

```python
from datetime import datetime, timedelta

@task
def extract_incremental(last_run: datetime) -> list:
    """Only extract data since last run."""
    return fetch_data_since(last_run)

@flow
def incremental_pipeline():
    # Get last successful run time
    last_run = get_last_successful_run()
    
    # Only process new data
    new_data = extract_incremental(last_run)
    
    if new_data:
        transformed = transform_data(new_data)
        load_data(transformed)
    else:
        print("No new data to process")
```

## Data Quality Checks

```python
@task
def validate_data(data: list) -> list:
    """Validate data quality."""
    # Check for required fields
    for record in data:
        assert 'id' in record, "Missing ID"
        assert 'amount' in record, "Missing amount"
        assert record['amount'] >= 0, "Negative amount"
    
    # Check for duplicates
    ids = [r['id'] for r in data]
    assert len(ids) == len(set(ids)), "Duplicate IDs found"
    
    # Check data volume
    assert len(data) > 0, "Empty dataset"
    assert len(data) < 10000000, "Unusually large dataset"
    
    return data

@flow
def pipeline_with_validation():
    raw = extract_data()
    validated = validate_data(raw)
    transformed = transform_data(validated)
    load_data(transformed)
```

## Checkpointing

```python
@flow
def pipeline_with_checkpoints():
    """Save progress at expensive steps."""
    
    # Expensive extraction
    if checkpoint_exists("extracted"):
        data = load_checkpoint("extracted")
    else:
        data = extract_data()  # Takes 30 minutes
        save_checkpoint("extracted", data)
    
    # Expensive transformation
    if checkpoint_exists("transformed"):
        transformed = load_checkpoint("transformed")
    else:
        transformed = transform_data(data)  # Takes 20 minutes
        save_checkpoint("transformed", transformed)
    
    # Quick load
    load_data(transformed)
    
    # Clean up on success
    delete_checkpoint("extracted")
    delete_checkpoint("transformed")
```

## Partitioning Strategy

```python
# Date partitioning
@task
def process_date_partition(date: str):
    """Process one day's data."""
    data = extract_data(date)
    transformed = transform_data(data)
    load_data(transformed, partition=date)

@flow
def backfill_pipeline(start_date: str, end_date: str):
    """Process multiple date partitions."""
    dates = generate_date_range(start_date, end_date)
    for date in dates:
        process_date_partition(date)
```

## Medallion Architecture (Bronze-Silver-Gold)

```python
@flow
def medallion_pipeline():
    # Bronze: Raw data
    raw_data = extract_from_source()
    write_to_layer("bronze", raw_data)
    
    # Silver: Cleaned, validated
    bronze_data = read_from_layer("bronze")
    cleaned = clean_and_validate(bronze_data)
    write_to_layer("silver", cleaned)
    
    # Gold: Aggregated, business logic
    silver_data = read_from_layer("silver")
    aggregated = aggregate_for_reporting(silver_data)
    write_to_layer("gold", aggregated)
```

## Monitoring and Alerting

```python
@task
def send_alert(message: str, level: str = "INFO"):
    """Send alert via email/slack."""
    if level == "ERROR":
        email.send(to="oncall@company.com", subject="Pipeline Error", body=message)
        slack.post(channel="#alerts", text=message)

@flow
def monitored_pipeline():
    start_time = datetime.now()
    
    try:
        data = extract_data()
        
        # Alert on data volume anomalies
        if len(data) < 100:
            send_alert(f"Low data volume: {len(data)}", "WARNING")
        
        transform_data(data)
        
        # Alert on success
        duration = (datetime.now() - start_time).seconds
        send_alert(f"Pipeline succeeded in {duration}s", "INFO")
        
    except Exception as e:
        send_alert(f"Pipeline failed: {e}", "ERROR")
        raise
```
