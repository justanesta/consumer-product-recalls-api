# dbt Testing Patterns

Patterns for testing dbt models with generic tests, singular tests, custom test macros, store_failures, and dbt unit tests.

## Generic Tests

### Built-in Generic Tests

```yaml
# models/marts/core.yml
version: 2
models:
  - name: dim_customers
    columns:
      - name: customer_id
        tests: [unique, not_null]
      - name: email
        tests: [unique, not_null]
      - name: customer_segment
        tests:
          - accepted_values:
              values: ["enterprise", "mid_market", "smb", "individual"]
      - name: account_manager_id
        tests:
          - relationships:
              to: ref('dim_employees')
              field: employee_id
```

### dbt-utils Generic Tests

```yaml
models:
  - name: fct_orders
    tests:
      - dbt_utils.expression_is_true:
          expression: "order_total >= 0"
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [order_date, customer_id, product_id]
    columns:
      - name: order_date
        tests:
          - dbt_utils.accepted_range:
              min_value: "'2020-01-01'"
              max_value: "current_date"
      - name: order_total
        tests:
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1000000
```

## Custom Generic Tests

### Writing a Custom Generic Test

```sql
-- tests/generic/test_is_valid_email.sql
{% test is_valid_email(model, column_name) %}
SELECT {{ column_name }}
FROM {{ model }}
WHERE {{ column_name }} IS NOT NULL
  AND {{ column_name }} NOT LIKE '%_@_%.__%'
{% endtest %}
```

### Custom Test with Parameters

```sql
-- tests/generic/test_row_count_in_range.sql
{% test row_count_in_range(model, min_count, max_count) %}
SELECT 1
FROM (SELECT COUNT(*) AS row_count FROM {{ model }}) sub
WHERE row_count < {{ min_count }} OR row_count > {{ max_count }}
{% endtest %}
```

```yaml
models:
  - name: fct_daily_revenue
    tests:
      - row_count_in_range:
          min_count: 100
          max_count: 10000
```

## Singular Tests

Singular tests are standalone SQL files that return failing rows.

### Business Rule Validation

```sql
-- tests/singular/test_revenue_never_negative.sql
SELECT order_id, order_date, revenue, order_status
FROM {{ ref('fct_orders') }}
WHERE revenue < 0 AND order_status = 'completed'
```

### Cross-Model Consistency

```sql
-- tests/singular/test_order_totals_match_line_items.sql
WITH order_totals AS (
    SELECT order_id, order_total FROM {{ ref('fct_orders') }}
),
line_item_totals AS (
    SELECT order_id, SUM(line_total) AS computed_total
    FROM {{ ref('fct_order_line_items') }}
    GROUP BY order_id
)
SELECT o.order_id, o.order_total, l.computed_total,
       ABS(o.order_total - l.computed_total) AS discrepancy
FROM order_totals o
JOIN line_item_totals l ON o.order_id = l.order_id
WHERE ABS(o.order_total - l.computed_total) > 0.01
```

### Timeliness Check

```sql
-- tests/singular/test_data_freshness.sql
SELECT MAX(updated_at) AS latest_record,
       DATEDIFF('hour', MAX(updated_at), CURRENT_TIMESTAMP) AS hours_stale
FROM {{ ref('stg_orders') }}
HAVING DATEDIFF('hour', MAX(updated_at), CURRENT_TIMESTAMP) > 48
```

## store_failures Configuration

### Global Configuration

```yaml
# dbt_project.yml
tests:
  +store_failures: true
  +schema: dbt_test_failures
  +severity: warn
```

### Per-Test Configuration

```yaml
columns:
  - name: amount
    tests:
      - not_null:
          config:
            store_failures: true
            schema: test_failures
            severity: warn
      - dbt_utils.accepted_range:
          min_value: 0
          config:
            store_failures: true
            severity: error
```

### Alerting on Stored Failures

```python
def check_failures(engine, failure_schema: str, threshold: int = 0):
    query = f"""
        SELECT table_name, row_count FROM (
            SELECT t.table_name,
                   (SELECT COUNT(*) FROM {failure_schema}.{t.table_name}) AS row_count
            FROM information_schema.tables t
            WHERE t.table_schema = '{failure_schema}'
        ) sub WHERE row_count > {threshold}
    """
    failures = pd.read_sql(query, engine)
    if len(failures) > 0:
        send_alert(f"dbt test failures detected:\n{failures.to_string()}")
    return failures
```

## dbt Unit Tests (dbt 1.8+)

### Basic Unit Test

```yaml
unit_tests:
  - name: test_payment_status_mapping
    model: stg_payments
    given:
      - input: source('stripe', 'payments')
        rows:
          - {payment_id: 1, status: 'succeeded', amount_cents: 1000}
          - {payment_id: 2, status: 'failed', amount_cents: 500}
    expect:
      rows:
        - {payment_id: 1, payment_status: 'completed', amount_dollars: 10.00}
        - {payment_id: 2, payment_status: 'failed', amount_dollars: 5.00}
```

### Unit Test with Overridden Macros

```yaml
unit_tests:
  - name: test_incremental_logic
    model: fct_events
    overrides:
      macros:
        is_incremental: true
    given:
      - input: ref('stg_events')
        rows:
          - {event_id: 1, event_type: 'click', created_at: '2025-03-01'}
          - {event_id: 2, event_type: 'view', created_at: '2025-03-02'}
      - input: this
        rows:
          - {event_id: 1, event_type: 'click', created_at: '2025-03-01'}
    expect:
      rows:
        - {event_id: 2, event_type: 'view', created_at: '2025-03-02'}
```

## Test Macros for Reusable Validation

```sql
-- macros/test_helpers/assert_metric_in_range.sql
{% macro assert_metric_in_range(model, metric_column, group_column, min_val, max_val) %}
SELECT {{ group_column }}, {{ metric_column }}
FROM {{ model }}
WHERE {{ metric_column }} < {{ min_val }} OR {{ metric_column }} > {{ max_val }}
{% endmacro %}
```

```sql
-- tests/singular/test_daily_revenue_bounds.sql
{{ assert_metric_in_range(
    model=ref('fct_daily_revenue'),
    metric_column='total_revenue',
    group_column='revenue_date',
    min_val=100, max_val=1000000
) }}
```

## Test Execution

```bash
# Run all tests
dbt test

# Run tests for a specific model
dbt test --select stg_orders

# Run by test type
dbt test --select "test_type:generic"
dbt test --select "test_type:singular"
dbt test --select "test_type:unit"

# Run tests downstream of a changed model
dbt test --select "stg_orders+"

# Run tests tagged as critical
dbt test --select "tag:critical"
```

### Test Severity Levels

```yaml
columns:
  - name: customer_id
    tests:
      - unique:
          config:
            severity: error          # Fail the pipeline
      - relationships:
          to: ref('dim_customers')
          field: customer_id
          config:
            severity: warn           # Log warning, don't block
            warn_if: ">10"
            error_if: ">100"
```

### Recommended Directory Layout

```
tests/
├── generic/                    # Custom reusable generic tests
│   ├── test_is_valid_email.sql
│   └── test_row_count_in_range.sql
├── singular/                   # One-off business rule tests
│   ├── test_revenue_never_negative.sql
│   └── test_order_totals_match_line_items.sql
└── unit/                       # dbt unit tests (YAML)
    ├── test_stg_orders.yml
    └── test_stg_payments.yml
```
