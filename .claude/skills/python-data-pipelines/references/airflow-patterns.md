# Airflow Patterns

## Basic DAG

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'email_on_failure': True,
    'email': ['alerts@example.com']
}

with DAG(
    'etl_pipeline',
    default_args=default_args,
    schedule_interval='0 0 * * *',
    start_date=datetime(2024, 1, 1),
    catchup=False
) as dag:
    
    extract = PythonOperator(
        task_id='extract',
        python_callable=extract_data
    )
    
    transform = PythonOperator(
        task_id='transform',
        python_callable=transform_data
    )
    
    load = PythonOperator(
        task_id='load',
        python_callable=load_data
    )
    
    extract >> transform >> load
```

## TaskFlow API (Modern Airflow)

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    schedule_interval='@daily',
    start_date=datetime(2024, 1, 1),
    catchup=False
)
def modern_etl():
    
    @task
    def extract():
        return {"data": [1, 2, 3]}
    
    @task
    def transform(data: dict):
        return {"transformed": data["data"]}
    
    @task
    def load(data: dict):
        print(f"Loading {data}")
    
    # Automatic XCom passing
    data = extract()
    transformed = transform(data)
    load(transformed)

modern_etl()
```

## Task Dependencies

```python
# Linear
task1 >> task2 >> task3

# Fan-out
start >> [task1, task2, task3]

# Fan-in
[task1, task2] >> end

# Complex
start >> task1 >> task2
start >> task3 >> task4
[task2, task4] >> end
```

## Branch Operator

```python
from airflow.operators.python import BranchPythonOperator

def choose_branch(**context):
    if context['execution_date'].day % 2 == 0:
        return 'even_day_task'
    return 'odd_day_task'

branch = BranchPythonOperator(
    task_id='branch',
    python_callable=choose_branch
)

even_task = PythonOperator(task_id='even_day_task', ...)
odd_task = PythonOperator(task_id='odd_day_task', ...)

branch >> [even_task, odd_task]
```

## Dynamic Task Generation

```python
from airflow.decorators import task

@dag(...)
def dynamic_dag():
    
    @task
    def get_sources():
        return ['source1', 'source2', 'source3']
    
    @task
    def process_source(source: str):
        print(f"Processing {source}")
    
    sources = get_sources()
    process_source.expand(source=sources)

dynamic_dag()
```

## Sensors for Waiting

```python
from airflow.sensors.filesystem import FileSensor

wait_for_file = FileSensor(
    task_id='wait_for_file',
    filepath='/data/input.csv',
    poke_interval=60,  # Check every 60 seconds
    timeout=3600  # Give up after 1 hour
)
```
