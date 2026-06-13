---
name: python-data-pipelines
description: |
  Data pipeline orchestration with Prefect and Airflow. Use this skill when building 
  ETL/ELT pipelines, need to choose orchestration tools, or designing data workflows. 
  Covers task dependencies, error handling, retries, scheduling, and best practices 
  for data pipeline architecture.
---

# Python Data Pipelines

Modern data pipeline orchestration patterns with Prefect and Airflow.

## Decision Matrix: Prefect vs Airflow

| Factor | Prefect | Airflow | Winner |
|--------|---------|---------|--------|
| **Learning curve** | Gentler (Pythonic) | Steeper (DAG syntax) | Prefect |
| **Dynamic workflows** | Native | Requires workarounds | Prefect |
| **Local development** | Excellent | Harder | Prefect |
| **Ecosystem maturity** | Newer (2018) | Mature (2014) | Airflow |

**General guidance**:
- **Use Prefect when**: New projects, want Pythonic API, dynamic workflows
- **Use Airflow when**: Existing Airflow org, need battle-tested tool

## Prefect Patterns

### Basic Task and Flow

```python
from prefect import task, flow

@task
def extract_data(source: str) -> list:
    return fetch_from_api(source)

@task
def transform_data(data: list) -> list:
    return [process_record(r) for r in data]

@flow(name="ETL Pipeline")
def etl_pipeline(source: str, destination: str):
    raw = extract_data(source)
    transformed = transform_data(raw)
    load_data(transformed, destination)
```

### Retries and Caching

```python
from datetime import timedelta
from prefect.tasks import task_input_hash

@task(
    retries=3,
    retry_delay_seconds=60,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=1)
)
def unreliable_api_call(endpoint: str):
    response = requests.get(endpoint)
    response.raise_for_status()
    return response.json()
```

See [prefect-patterns.md](references/prefect-patterns.md) for:
- Subflows
- Task results and artifacts
- Scheduling and deployment

## Airflow Patterns

### Basic DAG

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

with DAG(
    'etl_pipeline',
    schedule_interval='@daily',
    start_date=datetime(2024, 1, 1),
    catchup=False
) as dag:
    
    extract >> transform >> load
```

See [airflow-patterns.md](references/airflow-patterns.md) for:
- TaskFlow API (modern Airflow)
- Sensors for waiting
- Branch operators
- Dynamic task generation

## Pipeline Design Best Practices

### Idempotency

```python
# GOOD - Upsert based on key
def load_data(data):
    for record in data:
        db.upsert(record, key='id')
```

### Incremental Processing

```python
@task
def extract_incremental(last_run: datetime):
    return fetch_data_since(last_run)
```

### Data Quality Checks

```python
@task
def validate_data(data: list) -> list:
    for record in data:
        assert 'id' in record, "Missing ID"
        assert record['amount'] >= 0, "Negative amount"
    return data
```

See [pipeline-design-patterns.md](references/pipeline-design-patterns.md) for:
- Partitioning strategies
- Backfill patterns
- Monitoring and alerting

## Testing Pipelines

See [testing-pipelines.md](references/testing-pipelines.md) for:
- Mocking data sources
- Integration test patterns
- Local development setups

## Anti-Patterns to Avoid

| Avoid | Use Instead |
|-------|-------------|
| Non-idempotent operations | Upserts, delete-and-insert |
| Tightly coupled tasks | Clear interfaces |
| No error handling | Retries, alerts, checkpoints |

source: Prefect docs, Airflow docs
