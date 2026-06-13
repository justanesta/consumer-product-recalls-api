# SQL Transform Testing

Detailed patterns for testing SQL transformations using pytest, DuckDB, and dbt unit tests.

## pytest with DuckDB for Local SQL Testing

DuckDB provides an in-memory analytical database that requires no server setup, making it ideal for testing SQL transforms in CI/CD.

### Basic Setup

```python
import pytest
import duckdb
import pandas as pd

@pytest.fixture(scope="module")
def con():
    """Create a DuckDB in-memory connection shared across module tests."""
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()

@pytest.fixture
def seed_events(con):
    """Seed a clickstream events table."""
    con.execute("""
        CREATE OR REPLACE TABLE raw_events (
            event_id INTEGER,
            user_id INTEGER,
            event_type VARCHAR,
            page_url VARCHAR,
            event_timestamp TIMESTAMP,
            session_id VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO raw_events VALUES
        (1, 100, 'page_view', '/home', '2025-03-01 10:00:00', 'sess_a'),
        (2, 100, 'click', '/products', '2025-03-01 10:05:00', 'sess_a'),
        (3, 100, 'purchase', '/checkout', '2025-03-01 10:15:00', 'sess_a'),
        (4, 200, 'page_view', '/home', '2025-03-01 11:00:00', 'sess_b'),
        (5, 200, 'page_view', '/about', '2025-03-01 11:02:00', 'sess_b'),
        (6, 300, 'page_view', '/home', '2025-03-01 12:00:00', 'sess_c'),
        (7, 300, 'click', '/products', '2025-03-01 12:01:00', 'sess_c'),
        (8, 300, 'click', '/products/shoes', '2025-03-01 12:03:00', 'sess_c')
    """)
```

### Testing CTE Isolation

Extract and test individual CTEs from complex queries independently.

```python
def read_sql_file(path: str) -> str:
    with open(path) as f:
        return f.read()

def extract_cte(full_query: str, cte_name: str) -> str:
    """Extract a single CTE and make it a standalone query."""
    import re
    pattern = rf"{cte_name}\s+AS\s*\((.*?)\)(?:\s*,|\s*SELECT)"
    match = re.search(pattern, full_query, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"CTE '{cte_name}' not found in query")
    return match.group(1).strip()

def test_session_aggregation_cte(con, seed_events):
    """Test the session_stats CTE independently."""
    cte_sql = """
        SELECT
            session_id,
            user_id,
            COUNT(*) AS event_count,
            MIN(event_timestamp) AS session_start,
            MAX(event_timestamp) AS session_end,
            COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchases
        FROM raw_events
        GROUP BY session_id, user_id
    """
    result = con.execute(cte_sql).fetchdf()

    assert len(result) == 3
    sess_a = result[result["session_id"] == "sess_a"].iloc[0]
    assert sess_a["event_count"] == 3
    assert sess_a["purchases"] == 1

    sess_b = result[result["session_id"] == "sess_b"].iloc[0]
    assert sess_b["event_count"] == 2
    assert sess_b["purchases"] == 0
```

### Testing Window Functions

```python
def test_running_total_window(con, seed_transactions):
    query = """
        SELECT
            transaction_id,
            account_id,
            amount,
            SUM(amount) OVER (
                PARTITION BY account_id
                ORDER BY transaction_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS running_balance
        FROM transactions
        ORDER BY account_id, transaction_date
    """
    result = con.execute(query).fetchdf()

    acct_101 = result[result["account_id"] == 101]
    # Verify running total accumulates correctly
    assert acct_101["running_balance"].tolist() == [100.0, 250.0, 175.0]

def test_row_number_deduplication(con, seed_events):
    """Test dedup logic using ROW_NUMBER."""
    query = """
        SELECT * FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY user_id, event_type
                    ORDER BY event_timestamp DESC
                ) AS rn
            FROM raw_events
        )
        WHERE rn = 1
    """
    result = con.execute(query).fetchdf()

    # User 300 had two clicks, should keep only the latest
    user_300_clicks = result[
        (result["user_id"] == 300) & (result["event_type"] == "click")
    ]
    assert len(user_300_clicks) == 1
    assert user_300_clicks.iloc[0]["page_url"] == "/products/shoes"
```

## dbt Unit Tests

dbt unit tests (available in dbt 1.8+) let you test model logic with mock inputs.

### Basic dbt Unit Test

```yaml
# tests/unit/test_stg_orders.yml
unit_tests:
  - name: test_stg_orders_calculates_total
    model: stg_orders
    given:
      - input: ref('raw_orders')
        rows:
          - {order_id: 1, quantity: 3, unit_price: 10.00, discount: 0.1}
          - {order_id: 2, quantity: 1, unit_price: 50.00, discount: 0.0}
    expect:
      rows:
        - {order_id: 1, total_amount: 27.00}
        - {order_id: 2, total_amount: 50.00}
```

### Testing Models with Multiple Inputs

```yaml
unit_tests:
  - name: test_customer_lifetime_value
    model: customer_ltv
    given:
      - input: ref('stg_orders')
        rows:
          - {customer_id: 1, order_total: 100.00, order_date: '2025-01-01'}
          - {customer_id: 1, order_total: 200.00, order_date: '2025-02-01'}
          - {customer_id: 2, order_total: 50.00, order_date: '2025-01-15'}
      - input: ref('stg_customers')
        rows:
          - {customer_id: 1, signup_date: '2024-06-01', segment: 'premium'}
          - {customer_id: 2, signup_date: '2025-01-01', segment: 'standard'}
    expect:
      rows:
        - {customer_id: 1, total_spend: 300.00, order_count: 2, segment: 'premium'}
        - {customer_id: 2, total_spend: 50.00, order_count: 1, segment: 'standard'}
```

### Testing Edge Cases with Nulls and Duplicates

```yaml
unit_tests:
  - name: test_handles_null_discounts
    model: stg_orders
    given:
      - input: ref('raw_orders')
        rows:
          - {order_id: 1, quantity: 2, unit_price: 25.00, discount: null}
          - {order_id: 2, quantity: 1, unit_price: 10.00, discount: 0.5}
    expect:
      rows:
        - {order_id: 1, total_amount: 50.00}
        - {order_id: 2, total_amount: 5.00}

  - name: test_dedup_keeps_latest_order
    model: orders_deduped
    given:
      - input: ref('raw_orders')
        rows:
          - {order_id: 1, updated_at: '2025-01-01 10:00:00', status: 'pending'}
          - {order_id: 1, updated_at: '2025-01-01 12:00:00', status: 'completed'}
    expect:
      rows:
        - {order_id: 1, status: 'completed'}
```

## Testing Slowly Changing Dimensions

```python
def test_scd_type2_tracks_history(con):
    """Verify SCD Type 2 logic creates history rows correctly."""
    con.execute("""
        CREATE TABLE dim_customer_snapshot AS
        SELECT * FROM (VALUES
            (1, 'Alice', 'NYC', '2025-01-01'::DATE, '2025-02-28'::DATE, false),
            (1, 'Alice', 'LA',  '2025-03-01'::DATE, '9999-12-31'::DATE, true),
            (2, 'Bob',   'CHI', '2025-01-01'::DATE, '9999-12-31'::DATE, true)
        ) AS t(customer_id, name, city, valid_from, valid_to, is_current)
    """)

    # Current state should show only active records
    current = con.execute(
        "SELECT * FROM dim_customer_snapshot WHERE is_current = true"
    ).fetchdf()
    assert len(current) == 2
    assert current.loc[current["customer_id"] == 1, "city"].iloc[0] == "LA"

    # Full history for customer 1 should have 2 rows
    history = con.execute(
        "SELECT * FROM dim_customer_snapshot WHERE customer_id = 1 ORDER BY valid_from"
    ).fetchdf()
    assert len(history) == 2
    assert history.iloc[0]["city"] == "NYC"
    assert history.iloc[1]["city"] == "LA"
```

## Mock Data Patterns for SQL Tests

### Fixture Files with Parquet

```python
@pytest.fixture(scope="session")
def load_fixture_data():
    """Load fixtures from Parquet files for fast, typed test data."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    return {
        "orders": pd.read_parquet(fixtures_dir / "orders.parquet"),
        "customers": pd.read_parquet(fixtures_dir / "customers.parquet"),
        "products": pd.read_parquet(fixtures_dir / "products.parquet"),
    }

@pytest.fixture
def seed_all_tables(con, load_fixture_data):
    """Register all fixture DataFrames as DuckDB tables."""
    for table_name, df in load_fixture_data.items():
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
```

### Inline Fixture Helpers

```python
def make_order(order_id=1, customer_id=100, amount=50.0, status="completed"):
    return {"order_id": order_id, "customer_id": customer_id,
            "amount": amount, "status": status}

def test_refund_calculation(con):
    orders = [make_order(1, amount=100.0, status="refunded"),
              make_order(2, amount=200.0), make_order(3, amount=50.0, status="refunded")]
    df = pd.DataFrame(orders)
    con.execute("CREATE OR REPLACE TABLE orders AS SELECT * FROM df")
    result = con.execute("""
        SELECT SUM(amount) AS total_refunds FROM orders WHERE status = 'refunded'
    """).fetchdf()
    assert result["total_refunds"].iloc[0] == 150.0
```

## Running SQL Transform Tests

```bash
# Run all SQL transform tests
pytest tests/unit/sql/ -v

# Run with DuckDB verbose logging
pytest tests/unit/sql/ -v --log-cli-level=DEBUG

# Run dbt unit tests
dbt test --select "test_type:unit"

# Run specific dbt unit test
dbt test --select "test_stg_orders_calculates_total"
```
