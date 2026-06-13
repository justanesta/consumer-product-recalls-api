# Integration Testing for Data Pipelines

Patterns for end-to-end pipeline testing, staging environments, and CI/CD integration.

## Staging Environment Provisioning

### Isolated Schema Per Test Run

```python
import pytest
import uuid
from sqlalchemy import create_engine, text

@pytest.fixture(scope="session")
def staging_db():
    engine = create_engine(os.environ["STAGING_DATABASE_URL"])
    schema_name = f"test_{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema_name}"))
        conn.commit()
    yield engine, schema_name
    with engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA {schema_name} CASCADE"))
        conn.commit()
    engine.dispose()

@pytest.fixture
def seed_staging(staging_db):
    engine, schema = staging_db
    fixtures = load_fixtures("tests/fixtures/integration/")
    with engine.connect() as conn:
        for table_name, df in fixtures.items():
            df.to_sql(table_name, conn, schema=schema, if_exists="replace", index=False)
        conn.commit()
    return schema
```

### Using testcontainers-python

```python
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_engine():
    with PostgresContainer("postgres:16") as postgres:
        engine = create_engine(postgres.get_connection_url())
        yield engine
```

## End-to-End Pipeline Tests

```python
class TestDailyMetricsPipeline:
    def test_pipeline_succeeds(self, staging_db, seed_staging):
        engine, schema = staging_db
        result = run_daily_metrics(
            source_schema=schema, target_schema=schema,
            execution_date=date(2025, 3, 1), engine=engine,
        )
        assert result.status == "success"
        assert result.rows_processed > 0

    def test_output_schema_matches_contract(self, staging_db, seed_staging):
        engine, schema = staging_db
        run_daily_metrics(source_schema=schema, target_schema=schema,
                          execution_date=date(2025, 3, 1), engine=engine)
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = 'daily_metrics'
                ORDER BY ordinal_position
            """))
            columns = {row[0]: row[1] for row in result}
        expected = {"metric_date": "date", "region": "character varying",
                    "revenue": "numeric", "order_count": "integer"}
        assert columns == expected

    def test_pipeline_is_idempotent(self, staging_db, seed_staging):
        engine, schema = staging_db
        for _ in range(2):
            run_daily_metrics(source_schema=schema, target_schema=schema,
                              execution_date=date(2025, 3, 1), engine=engine)
        with engine.connect() as conn:
            count = conn.execute(text(
                f"SELECT COUNT(*) FROM {schema}.daily_metrics WHERE metric_date = '2025-03-01'"
            )).scalar()
            distinct = conn.execute(text(
                f"SELECT COUNT(DISTINCT region) FROM {schema}.daily_metrics WHERE metric_date = '2025-03-01'"
            )).scalar()
        assert count == distinct

    def test_handles_empty_source(self, staging_db):
        engine, schema = staging_db
        result = run_daily_metrics(source_schema=schema, target_schema=schema,
                                   execution_date=date(2025, 3, 1), engine=engine)
        assert result.status == "success"
        assert result.rows_processed == 0
```

## Testing Airflow DAGs

```python
from airflow.models import DagBag

@pytest.fixture(scope="session")
def dagbag():
    return DagBag(dag_folder="dags/", include_examples=False)

def test_no_import_errors(dagbag):
    assert len(dagbag.import_errors) == 0, f"DAG import errors: {dagbag.import_errors}"

def test_dag_has_expected_tasks(dagbag):
    dag = dagbag.get_dag("daily_revenue_pipeline")
    task_ids = [t.task_id for t in dag.tasks]
    assert "extract_orders" in task_ids
    assert "transform_revenue" in task_ids
    assert "load_to_warehouse" in task_ids

def test_dag_dependencies(dagbag):
    dag = dagbag.get_dag("daily_revenue_pipeline")
    extract = dag.get_task("extract_orders")
    transform = dag.get_task("transform_revenue")
    assert transform.task_id in [t.task_id for t in extract.downstream_list]
```

## Testing Prefect Flows

```python
from prefect.testing.utilities import prefect_test_harness

@pytest.fixture(scope="session", autouse=True)
def prefect_test_env():
    with prefect_test_harness():
        yield

def test_etl_flow_completes(seed_staging):
    from myproject.flows.daily_etl import daily_etl_flow
    state = daily_etl_flow(source_schema=seed_staging, execution_date="2025-03-01")
    assert state.is_completed()

def test_etl_flow_retries_on_transient_error(seed_staging):
    with patch("myproject.flows.daily_etl.extract_data") as mock_extract:
        mock_extract.side_effect = [ConnectionError("timeout"), pd.DataFrame({"a": [1]})]
        state = daily_etl_flow(source_schema=seed_staging, execution_date="2025-03-01")
        assert state.is_completed()
        assert mock_extract.call_count == 2
```

## Transaction Rollback Pattern

```python
@pytest.fixture
def db_session(staging_db):
    engine, schema = staging_db
    connection = engine.connect()
    transaction = connection.begin()
    yield connection, schema
    transaction.rollback()
    connection.close()

def test_insert_does_not_persist(db_session):
    conn, schema = db_session
    conn.execute(text(f"INSERT INTO {schema}.orders VALUES (999, 100, 50.0, 'test')"))
    count = conn.execute(text(
        f"SELECT COUNT(*) FROM {schema}.orders WHERE order_id = 999"
    )).scalar()
    assert count == 1
    # After test completes, rollback undoes the insert automatically
```

## CI/CD Integration

### GitHub Actions Configuration

```yaml
name: Pipeline Integration Tests
on:
  pull_request:
    paths: ["dags/**", "models/**", "pipelines/**"]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-test.txt
      - run: pytest tests/integration/ -v --tb=short -x
        env:
          STAGING_DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
```

### Test Execution Order

```python
# conftest.py
def pytest_collection_modifyitems(items):
    """Run unit tests before integration tests."""
    unit_tests = [i for i in items if "unit" in str(i.fspath)]
    integration_tests = [i for i in items if "integration" in str(i.fspath)]
    items[:] = unit_tests + integration_tests
```
