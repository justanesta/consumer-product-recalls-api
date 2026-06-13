# Prefect Patterns

## Basic Flow and Tasks

```python
from prefect import flow, task

@task
def extract_data(source: str) -> list:
    """Extract data from source."""
    data = fetch_from_api(source)
    return data

@task
def transform_data(data: list) -> list:
    """Transform the data."""
    return [process_record(r) for r in data]

@task
def load_data(data: list, destination: str):
    """Load data to destination."""
    write_to_database(data, destination)

@flow(name="ETL Pipeline")
def etl_pipeline(source: str, destination: str):
    """Main ETL workflow."""
    raw = extract_data(source)
    transformed = transform_data(raw)
    load_data(transformed, destination)

# Run locally
if __name__ == "__main__":
    etl_pipeline("api.example.com", "postgres://db")
```

## Parallel Execution

```python
@flow
def parallel_processing():
    # Submit tasks for parallel execution
    future1 = extract_data.submit("source1")
    future2 = extract_data.submit("source2")
    future3 = extract_data.submit("source3")
    
    # Wait for results
    data1 = future1.result()
    data2 = future2.result()
    data3 = future3.result()
    
    # Process combined data
    all_data = data1 + data2 + data3
    load_data(all_data, "destination")
```

## Retries and Caching

```python
from datetime import timedelta
from prefect.tasks import task_input_hash

@task(
    retries=3,
    retry_delay_seconds=60,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=1)
)
def unreliable_api_call(endpoint: str) -> dict:
    """Task with retries and caching."""
    response = requests.get(endpoint)
    response.raise_for_status()
    return response.json()
```

## Error Handling

```python
from prefect.exceptions import FlowFailed

@flow
def resilient_pipeline():
    try:
        data = extract_data("source")
        transform_data(data)
    except Exception as e:
        send_alert(f"Pipeline failed: {e}")
        raise FlowFailed(f"ETL failed: {e}")
```

## Subflows

```python
@flow
def data_quality_check(data: list) -> bool:
    """Subflow for data quality checks."""
    return len(data) > 0 and all("id" in r for r in data)

@flow
def main_pipeline():
    data = extract_data("source")
    
    # Call subflow
    if data_quality_check(data):
        transform_data(data)
    else:
        raise ValueError("Data quality check failed")
```

## Scheduling

```python
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule

deployment = Deployment.build_from_flow(
    flow=etl_pipeline,
    name="daily-etl",
    schedule=CronSchedule(cron="0 0 * * *")  # Daily at midnight
)

deployment.apply()
```

## Parameters and Artifacts

```python
@flow
def parameterized_flow(
    source: str = "default_source",
    batch_size: int = 1000
):
    data = extract_data(source)
    
    # Save artifact for inspection
    from prefect.artifacts import create_markdown_artifact
    
    create_markdown_artifact(
        key="data-summary",
        markdown=f"Processed {len(data)} records"
    )
    
    return data
```
