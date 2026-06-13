# View Patterns

## Simple Views

```sql
-- Basic view encapsulating a common query
CREATE OR REPLACE VIEW v_active_employees AS
SELECT
    employee_id,
    first_name,
    last_name,
    email,
    department_id,
    hire_date,
    salary
FROM employees
WHERE termination_date IS NULL
  AND status = 'active';

-- View with computed columns
CREATE OR REPLACE VIEW v_employee_directory AS
SELECT
    e.employee_id,
    e.first_name || ' ' || e.last_name AS full_name,
    e.email,
    d.department_name,
    m.first_name || ' ' || m.last_name AS manager_name,
    DATE_PART('year', AGE(CURRENT_DATE, e.hire_date)) AS years_of_service
FROM employees e
INNER JOIN departments d ON e.department_id = d.department_id
LEFT JOIN employees m ON e.manager_id = m.employee_id
WHERE e.termination_date IS NULL;
```

## Complex Views with Business Logic

```sql
-- Customer 360 view aggregating from multiple tables
CREATE OR REPLACE VIEW v_customer_360 AS
SELECT
    c.customer_id,
    c.customer_name,
    c.email,
    c.signup_date,
    COALESCE(os.total_orders, 0) AS total_orders,
    COALESCE(os.total_spent, 0.00) AS total_spent,
    COALESCE(os.avg_order_value, 0.00) AS avg_order_value,
    os.last_order_date,
    CASE
        WHEN os.last_order_date >= CURRENT_DATE - INTERVAL '30 days' THEN 'Active'
        WHEN os.last_order_date >= CURRENT_DATE - INTERVAL '90 days' THEN 'At Risk'
        WHEN os.last_order_date IS NOT NULL THEN 'Churned'
        ELSE 'Never Purchased'
    END AS engagement_status,
    COALESCE(t.open_tickets, 0) AS open_support_tickets
FROM customers c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS total_orders,
        SUM(total_amount) AS total_spent,
        AVG(total_amount) AS avg_order_value,
        MAX(order_date) AS last_order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status != 'cancelled'
) os ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS open_tickets
    FROM support_tickets st
    WHERE st.customer_id = c.customer_id
      AND st.status IN ('open', 'in_progress')
) t ON TRUE;
```

## Updatable Views

```sql
-- Simple updatable view (single table, no aggregates)
CREATE OR REPLACE VIEW v_us_customers AS
SELECT customer_id, customer_name, email, city, state
FROM customers
WHERE country = 'US';

-- INSERT through the view works because it maps to a single table
INSERT INTO v_us_customers (customer_name, email, city, state)
VALUES ('Jane Doe', 'jane@example.com', 'Austin', 'TX');

-- WITH CHECK OPTION prevents inserting rows that violate the view filter
CREATE OR REPLACE VIEW v_us_customers_checked AS
SELECT customer_id, customer_name, email, city, state, country
FROM customers
WHERE country = 'US'
WITH CHECK OPTION;

-- This fails: country = 'CA' violates the WHERE clause
INSERT INTO v_us_customers_checked (customer_name, email, city, state, country)
VALUES ('Jean Dupont', 'jean@example.com', 'Montreal', 'QC', 'CA');
-- ERROR: new row violates check option for view "v_us_customers_checked"

-- LOCAL vs CASCADED check option
CREATE VIEW v_active_us_customers AS
SELECT * FROM v_us_customers_checked
WHERE status = 'active'
WITH CASCADED CHECK OPTION;
-- CASCADED: enforces checks on this view AND all underlying views
-- LOCAL: only enforces the check on this view's own WHERE
```

## Security and Row-Level Access Views

```sql
-- PostgreSQL: security barrier view prevents leaking data through functions
CREATE OR REPLACE VIEW v_my_department_employees
WITH (security_barrier = true) AS
SELECT employee_id, first_name, last_name, email, salary
FROM employees
WHERE department_id = (
    SELECT department_id FROM employees WHERE employee_id = current_setting('app.current_user_id')::int
);

-- Grant access through the view, not the underlying table
REVOKE ALL ON employees FROM app_user;
GRANT SELECT ON v_my_department_employees TO app_user;
```

## SQL Server Specific Patterns

```sql
-- SQL Server: schema-bound view for deterministic indexing
CREATE VIEW dbo.v_order_totals
WITH SCHEMABINDING
AS
SELECT
    o.customer_id,
    COUNT_BIG(*) AS order_count,
    SUM(o.total_amount) AS total_spent
FROM dbo.orders o
GROUP BY o.customer_id;
GO

-- Create clustered index on schema-bound view (indexed view)
CREATE UNIQUE CLUSTERED INDEX idx_v_order_totals
    ON dbo.v_order_totals (customer_id);
GO
```

## MySQL Specific Patterns

```sql
-- MySQL: algorithm hint for view execution
CREATE ALGORITHM = MERGE VIEW v_recent_orders AS
SELECT order_id, customer_id, order_date, total_amount
FROM orders
WHERE order_date >= CURRENT_DATE - INTERVAL 30 DAY;
-- MERGE: integrates view SQL into outer query (preferred for performance)
-- TEMPTABLE: materializes view into a temp table (required for aggregates)
-- UNDEFINED: let MySQL choose (default)

-- MySQL: definer vs invoker security
CREATE DEFINER = 'admin'@'localhost'
SQL SECURITY INVOKER
VIEW v_employee_public AS
SELECT employee_id, first_name, last_name, department_id
FROM employees;
-- DEFINER: executes with the creator's permissions (default)
-- INVOKER: executes with the calling user's permissions
```

## View Dependency Management

```sql
-- PostgreSQL: find all views depending on a table
SELECT DISTINCT
    dependent_ns.nspname AS view_schema,
    dependent_view.relname AS view_name
FROM pg_depend
JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
JOIN pg_class AS dependent_view ON pg_rewrite.ev_class = dependent_view.oid
JOIN pg_class AS source_table ON pg_depend.refobjid = source_table.oid
JOIN pg_namespace AS dependent_ns ON dependent_view.relnamespace = dependent_ns.oid
JOIN pg_namespace AS source_ns ON source_table.relnamespace = source_ns.oid
WHERE source_ns.nspname = 'public'
  AND source_table.relname = 'orders'
  AND dependent_view.relname != source_table.relname;

-- Safe column rename: check dependencies before ALTER
-- PostgreSQL: CASCADE drops dependent views (dangerous!)
ALTER TABLE orders RENAME COLUMN total_amount TO order_total;
-- Any view referencing total_amount will break

-- Preferred: CREATE OR REPLACE to update views in place
CREATE OR REPLACE VIEW v_order_summary AS
SELECT order_id, customer_id, order_total  -- renamed column
FROM orders;
```

## Nested and Layered Views

```sql
-- Layer 1: raw data cleaning
CREATE OR REPLACE VIEW v_clean_orders AS
SELECT
    order_id,
    customer_id,
    order_date,
    COALESCE(total_amount, 0) AS total_amount,
    COALESCE(status, 'unknown') AS status
FROM raw_orders
WHERE order_date IS NOT NULL;

-- Layer 2: business logic
CREATE OR REPLACE VIEW v_completed_orders AS
SELECT * FROM v_clean_orders
WHERE status = 'completed';

-- Layer 3: aggregation for reporting
CREATE OR REPLACE VIEW v_daily_revenue AS
SELECT
    order_date,
    COUNT(*) AS order_count,
    SUM(total_amount) AS daily_revenue
FROM v_completed_orders
GROUP BY order_date;

-- WARNING: deeply nested views (3+ levels) can hide performance problems.
-- Always run EXPLAIN on queries against layered views to verify the plan.
```

## Drop and Replace Patterns

```sql
-- PostgreSQL: CREATE OR REPLACE preserves grants and dependent objects
-- (only works if column list is compatible)
CREATE OR REPLACE VIEW v_active_employees AS
SELECT employee_id, first_name, last_name, email, department_id, hire_date
FROM employees
WHERE termination_date IS NULL;

-- If you need to change the column list, drop and recreate
DROP VIEW IF EXISTS v_active_employees CASCADE;
-- CASCADE drops dependent views too — always check dependencies first

-- SQL Server: use DROP IF EXISTS + CREATE
DROP VIEW IF EXISTS dbo.v_active_employees;
GO
CREATE VIEW dbo.v_active_employees AS
SELECT employee_id, first_name, last_name, email, department_id, hire_date
FROM employees
WHERE termination_date IS NULL;
GO
```
