---
name: data-eng-testing-patterns
description: |
  Testing patterns for data engineering pipelines and transformations. Use this skill when
  writing tests for SQL transforms, dbt models, data contracts, pipeline integration tests,
  or managing test data. Covers pytest-sql, dbt testing, contract testing, regression
  testing, and synthetic data generation for reliable data infrastructure.
---

# Data Engineering Testing Patterns

Comprehensive testing strategies for data pipelines, SQL transformations, and data contracts.

## Core Principles

1. **Test data, not just code** - Validate row counts, schema shapes, value distributions, and business rules alongside logic
2. **Data contracts are boundaries** - Every producer/consumer interface needs explicit schema and semantic contracts
3. **Idempotent test fixtures** - Tests must create, validate, and tear down their own state without side effects
4. **Test at multiple granularities** - Unit test individual transforms, integration test pipeline stages, end-to-end test full workflows
5. **Fail fast with clear diagnostics** - Store test failures with sample rows so debugging does not require re-running the full pipeline

## Unit Testing SQL Transforms

**Use pytest with DuckDB to validate individual transformations in memory**

```python
import pytest
import pandas as pd
from sqlalchemy import create_engine, text

@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine("duckdb:///:memory:")
    yield engine
    engine.dispose()

@pytest.fixture
def seed_orders(test_engine):
    df = pd.DataFrame({
        "order_id": [1, 2, 3],
        "customer_id": [101, 101, 102],
        "amount": [50.00, 75.00, 200.00],
        "status": ["completed", "completed", "refunded"],
    })
    df.to_sql("orders", test_engine, if_exists="replace", index=False)
    return df

def test_revenue_excludes_refunds(test_engine, seed_orders):
    result = pd.read_sql(text("""
        SELECT customer_id, SUM(amount) AS total_revenue
        FROM orders WHERE status != 'refunded'
        GROUP BY customer_id
    """), test_engine)
    assert len(result) == 1
    assert result.iloc[0]["total_revenue"] == 125.00
```

See [sql-transform-testing.md](references/sql-transform-testing.md) for:
- CTE isolation testing
- dbt unit test patterns with mock inputs
- Testing window functions and complex aggregations
- Snapshot and slowly changing dimension tests

## Integration Testing Pipelines

**Validate end-to-end pipeline execution against isolated staging schemas**

```python
@pytest.fixture(scope="session")
def staging_warehouse():
    engine = create_engine(os.environ["STAGING_DB_URL"])
    schema = f"test_{uuid.uuid4().hex[:8]}"
    engine.execute(f"CREATE SCHEMA {schema}")
    yield engine, schema
    engine.execute(f"DROP SCHEMA {schema} CASCADE")

def test_daily_revenue_end_to_end(staging_warehouse):
    engine, schema = staging_warehouse
    seed_test_data(engine, schema, fixture="daily_revenue_input.json")

    result = daily_revenue_pipeline(
        source_schema=schema, target_schema=schema, execution_date="2025-03-01",
    )
    assert result.status == "success"

    output = pd.read_sql(f"SELECT * FROM {schema}.revenue_daily", engine)
    assert len(output) > 0
    assert output["revenue"].sum() > 0
```

See [integration-testing.md](references/integration-testing.md) for:
- Staging environment provisioning and teardown
- Testing Airflow/Prefect DAGs locally
- Database transaction rollback patterns
- CI/CD integration with containerized warehouses

## dbt Testing Patterns

**Use generic tests, singular tests, and store_failures for production reliability**

```yaml
# models/staging/stg_orders.yml
version: 2
models:
  - name: stg_orders
    columns:
      - name: order_id
        tests: [unique, not_null]
      - name: status
        tests:
          - accepted_values:
              values: ["completed", "pending", "refunded", "cancelled"]
      - name: amount
        tests:
          - not_null
          - dbt_utils.expression_is_true:
              expression: ">= 0"
              config:
                store_failures: true
                schema: test_failures
```

See [dbt-testing-patterns.md](references/dbt-testing-patterns.md) for:
- Writing custom generic tests
- Singular tests for complex business rules
- store_failures configuration and monitoring
- dbt unit tests with mock refs and sources
- Test macros for reusable validation logic

## Data Contract Testing

**Enforce schema and semantic contracts between producers and consumers**

```python
@dataclass
class DataContract:
    name: str
    version: str
    schema: dict
    semantic_rules: list

    def validate_schema(self, df: pd.DataFrame) -> list[str]:
        errors = []
        for col, spec in self.schema["columns"].items():
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")
            elif not pd.api.types.is_dtype_equal(df[col].dtype, spec["dtype"]):
                errors.append(f"{col}: expected {spec['dtype']}, got {df[col].dtype}")
        return errors

    def validate_semantics(self, df: pd.DataFrame) -> list[str]:
        errors = []
        for rule in self.semantic_rules:
            failing = df.query(f"not ({rule['expression']})")
            if len(failing) > 0:
                errors.append(f"Rule '{rule['name']}' failed on {len(failing)} rows")
        return errors

def test_orders_contract(orders_df):
    contract = DataContract(
        name="orders", version="2.1.0",
        schema=load_contract("contracts/orders_v2.json"),
        semantic_rules=[
            {"name": "positive_amount", "expression": "amount >= 0"},
        ],
    )
    assert not contract.validate_schema(orders_df)
    assert not contract.validate_semantics(orders_df)
```

See [data-contract-patterns.md](references/data-contract-patterns.md) for:
- JSON Schema and Avro contract definitions
- Backward and forward compatibility checks
- Contract versioning strategies
- Producer and consumer test responsibilities

## Pipeline Regression Testing

**Detect unexpected changes in pipeline output across code changes**

```python
import hashlib

def compute_output_fingerprint(df: pd.DataFrame, key_columns: list[str]) -> str:
    sorted_df = df.sort_values(key_columns).reset_index(drop=True)
    return hashlib.sha256(sorted_df.to_csv(index=False).encode()).hexdigest()

class TestRevenueRegression:
    EXPECTED_HASH = "a3f2b8c1d4e5..."

    def test_output_matches_baseline(self, pipeline_output):
        actual = compute_output_fingerprint(pipeline_output, ["date", "region"])
        assert actual == self.EXPECTED_HASH, "Output changed. Update hash if intentional."

    def test_row_count_within_bounds(self, pipeline_output):
        assert 900 <= len(pipeline_output) <= 1100
```

## Test Data Management

**Use factories and synthetic data for reproducible tests**

```python
from faker import Faker
import numpy as np

fake = Faker()
Faker.seed(42)
np.random.seed(42)

def generate_orders(n: int = 1000, anomaly_rate: float = 0.02) -> pd.DataFrame:
    orders = []
    for i in range(n):
        is_anomaly = np.random.random() < anomaly_rate
        orders.append({
            "order_id": i + 1,
            "customer_id": fake.random_int(min=1000, max=9999),
            "amount": round(np.random.lognormal(4, 1), 2) if not is_anomaly else -99.99,
            "status": np.random.choice(["completed", "pending", "refunded"], p=[0.7, 0.2, 0.1]),
        })
    return pd.DataFrame(orders)
```

See [test-data-management.md](references/test-data-management.md) for:
- Factory patterns for complex nested data
- Data anonymization for production-like test sets
- Fixture file organization (JSON, CSV, Parquet)
- Seeded random generation for reproducibility

## Anti-Patterns

| Avoid | Use Instead |
|-------|-------------|
| Testing against production data directly | Synthetic data with known properties |
| Shared mutable test state across tests | Isolated fixtures with setup/teardown |
| Only testing happy paths | Include nulls, duplicates, edge cases, and anomalies |
| Hardcoded connection strings in tests | Environment variables or test config fixtures |
| Skipping schema validation | Data contract tests on every pipeline run |
| Testing SQL by reading query strings | Execute queries against test data and validate results |

## Performance

- **Use DuckDB for local SQL tests** - In-memory analytical queries without a database server
- **Scope expensive fixtures to session** - Database connections, schema provisioning, large data generation
- **Parallelize with pytest-xdist** - Run independent test modules across workers with `pytest -n auto`
- **Use Parquet fixtures over CSV** - Faster reads, type preservation, smaller files
- **Limit integration test data volume** - Use representative samples (500-1000 rows) rather than full datasets

source: dbt docs, Great Expectations docs, pytest-sql patterns, Data Contract specification
