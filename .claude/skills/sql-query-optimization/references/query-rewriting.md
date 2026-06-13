# Query Rewriting Techniques

Patterns for restructuring SQL queries to improve performance without changing results.

## EXISTS vs IN

Both check for the existence of matching rows, but they differ in performance and NULL handling.

### Performance Characteristics

```sql
-- IN: executes the subquery, builds a result set, then checks membership
-- Efficient when the subquery result set is small
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id FROM orders o WHERE o.total_amount > 500
);

-- EXISTS: for each outer row, checks if the correlated subquery returns at least one row
-- Short-circuits on first match; efficient when the inner table is indexed
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.total_amount > 500
);
```

**When to use which:**
- **EXISTS** is typically faster when the inner table is large and indexed on the correlation column
- **IN** is typically faster when the subquery returns a small, distinct set of values
- Modern optimizers (PostgreSQL 12+, SQL Server 2016+) often transform one into the other automatically

### NULL Behavior Difference

```sql
-- CRITICAL: NOT IN fails silently when the subquery contains NULLs
-- If ANY value in the subquery is NULL, NOT IN returns zero rows
SELECT * FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id FROM blacklist  -- if any row has customer_id = NULL
);
-- Returns EMPTY result set (not what you expect!)

-- NOT EXISTS handles NULLs correctly
SELECT * FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM blacklist b WHERE b.customer_id = c.customer_id
);
-- Returns customers not in the blacklist, regardless of NULLs

-- LEFT JOIN alternative (also NULL-safe)
SELECT c.*
FROM customers c
LEFT JOIN blacklist b ON c.customer_id = b.customer_id
WHERE b.customer_id IS NULL;
```

## CTE Materialization

In PostgreSQL 12+, simple CTEs may be inlined (optimized as subqueries). You can control this behavior.

```sql
-- PostgreSQL: CTE is inlined by default if referenced once and not recursive
WITH recent_orders AS (
    SELECT * FROM orders WHERE order_date >= '2025-01-01'
)
SELECT * FROM recent_orders WHERE status = 'shipped';
-- Optimizer may push status = 'shipped' into the CTE scan -> good

-- Force materialization (creates a temp result set)
WITH recent_orders AS MATERIALIZED (
    SELECT * FROM orders WHERE order_date >= '2025-01-01'
)
SELECT * FROM recent_orders WHERE status = 'shipped';
-- CTE result is computed first, then filtered -> may be slower

-- Force inlining (prevent materialization)
WITH recent_orders AS NOT MATERIALIZED (
    SELECT * FROM orders WHERE order_date >= '2025-01-01'
)
SELECT * FROM recent_orders WHERE status = 'shipped';
```

**When materialization helps:**
- The CTE is referenced multiple times and is expensive to compute
- You want to prevent the optimizer from choosing a bad plan after inlining

**When materialization hurts:**
- The CTE produces many rows but the outer query filters most of them
- Materialization prevents predicate pushdown into the CTE

```sql
-- MySQL: CTEs are always materialized (as of MySQL 8.0)
-- This means predicates from the outer query are NOT pushed into the CTE
-- Workaround: move the filter inside the CTE

-- SLOW in MySQL: filter not pushed down
WITH all_orders AS (
    SELECT * FROM orders
)
SELECT * FROM all_orders WHERE order_date >= '2025-01-01';

-- FAST in MySQL: filter inside the CTE
WITH recent_orders AS (
    SELECT * FROM orders WHERE order_date >= '2025-01-01'
)
SELECT * FROM recent_orders;
```

## LATERAL Joins

LATERAL allows a subquery in FROM to reference columns from preceding tables. It replaces correlated subqueries in the SELECT list with a more efficient join pattern.

```sql
-- SLOW: correlated subquery in SELECT executes once per customer row (N+1)
SELECT
    c.customer_id,
    c.customer_name,
    (SELECT MAX(o.order_date)
     FROM orders o
     WHERE o.customer_id = c.customer_id) AS last_order_date,
    (SELECT SUM(o.total_amount)
     FROM orders o
     WHERE o.customer_id = c.customer_id) AS lifetime_value
FROM customers c
WHERE c.region = 'US-West';
-- Two correlated subqueries -> 2 * N executions for N customers

-- FAST: LATERAL join computes both values in a single pass per customer
SELECT
    c.customer_id,
    c.customer_name,
    order_stats.last_order_date,
    order_stats.lifetime_value
FROM customers c
CROSS JOIN LATERAL (
    SELECT
        MAX(o.order_date) AS last_order_date,
        SUM(o.total_amount) AS lifetime_value
    FROM orders o
    WHERE o.customer_id = c.customer_id
) AS order_stats
WHERE c.region = 'US-West';
```

```sql
-- LATERAL for "top-N per group" (more efficient than window functions for small N)
-- Get the 3 most recent orders for each active customer
SELECT c.customer_id, c.customer_name,
       recent.order_id, recent.order_date, recent.total_amount
FROM customers c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.order_date, o.total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC
    LIMIT 3
) AS recent
WHERE c.status = 'active';
-- Uses an index on orders(customer_id, order_date DESC) efficiently
-- Only fetches 3 rows per customer, not the entire orders table
```

```sql
-- SQL Server equivalent: CROSS APPLY / OUTER APPLY
SELECT c.customer_id, c.customer_name,
       recent.order_id, recent.order_date
FROM customers c
CROSS APPLY (
    SELECT TOP 3 o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC
) AS recent;

-- OUTER APPLY includes customers with no matching orders (like LEFT JOIN LATERAL)
```

## Replacing Correlated Subqueries with JOINs

```sql
-- SLOW: correlated subquery runs for each row in the outer query
SELECT
    p.product_id,
    p.product_name,
    p.price,
    (SELECT AVG(p2.price)
     FROM products p2
     WHERE p2.category_id = p.category_id) AS category_avg_price
FROM products p;

-- FAST: compute the aggregate once, then join
SELECT
    p.product_id,
    p.product_name,
    p.price,
    ca.avg_price AS category_avg_price
FROM products p
JOIN (
    SELECT category_id, AVG(price) AS avg_price
    FROM products
    GROUP BY category_id
) ca ON ca.category_id = p.category_id;
```

## Batch Operations

Replace row-at-a-time processing with set-based operations.

```sql
-- SLOW: updating rows one at a time in application code
-- for each order_id in list:
--     UPDATE orders SET status = 'archived' WHERE order_id = ?;

-- FAST: single batch UPDATE
UPDATE orders
SET status = 'archived'
WHERE order_date < '2024-01-01'
  AND status = 'delivered';

-- For very large updates, batch in chunks to avoid long locks
-- PostgreSQL: use a CTE with LIMIT
WITH batch AS (
    SELECT order_id FROM orders
    WHERE order_date < '2024-01-01' AND status = 'delivered'
    LIMIT 10000
    FOR UPDATE SKIP LOCKED
)
UPDATE orders
SET status = 'archived'
WHERE order_id IN (SELECT order_id FROM batch);
-- Run this in a loop until 0 rows affected
```

```sql
-- SLOW: INSERT one row at a time
INSERT INTO log_entries (event_type, payload) VALUES ('click', '{}');
INSERT INTO log_entries (event_type, payload) VALUES ('view', '{}');
INSERT INTO log_entries (event_type, payload) VALUES ('purchase', '{}');

-- FAST: multi-row INSERT
INSERT INTO log_entries (event_type, payload)
VALUES
    ('click', '{}'),
    ('view', '{}'),
    ('purchase', '{}');
-- Batch size of 1000-5000 rows typically optimal for network round-trips
```

## UNION vs UNION ALL

```sql
-- UNION: removes duplicates (requires sort or hash)
SELECT customer_id FROM orders WHERE status = 'shipped'
UNION
SELECT customer_id FROM returns WHERE status = 'completed';

-- UNION ALL: keeps duplicates (no dedup overhead)
SELECT customer_id FROM orders WHERE status = 'shipped'
UNION ALL
SELECT customer_id FROM returns WHERE status = 'completed';

-- Use UNION ALL when:
-- 1. You know the sets are disjoint (no duplicates possible)
-- 2. Duplicates are acceptable
-- 3. You will apply DISTINCT or GROUP BY on the outer query anyway
```

## Replacing DISTINCT with GROUP BY or EXISTS

```sql
-- SLOW: DISTINCT on a large result set requires sorting all rows
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_date >= '2025-01-01';

-- FASTER: EXISTS avoids the join explosion and dedup
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_date >= '2025-01-01'
);
-- No duplicates generated in the first place
```

## Window Functions vs Self-Joins

```sql
-- SLOW: self-join to compare each row with its predecessor
SELECT
    a.order_id, a.order_date, a.total_amount,
    a.total_amount - b.total_amount AS change_from_previous
FROM orders a
LEFT JOIN orders b ON b.order_id = (
    SELECT MAX(o.order_id) FROM orders o
    WHERE o.order_id < a.order_id AND o.customer_id = a.customer_id
)
WHERE a.customer_id = 42;

-- FAST: window function reads data in a single pass
SELECT
    order_id, order_date, total_amount,
    total_amount - LAG(total_amount) OVER (
        PARTITION BY customer_id ORDER BY order_date
    ) AS change_from_previous
FROM orders
WHERE customer_id = 42;
```

## Conditional Aggregation vs Multiple Queries

```sql
-- SLOW: three separate queries
SELECT COUNT(*) FROM orders WHERE status = 'pending';
SELECT COUNT(*) FROM orders WHERE status = 'shipped';
SELECT COUNT(*) FROM orders WHERE status = 'delivered';

-- FAST: single scan with conditional aggregation
SELECT
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
    COUNT(*) FILTER (WHERE status = 'shipped') AS shipped_count,
    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered_count
FROM orders;
-- PostgreSQL FILTER syntax; use CASE for cross-database:
-- COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending_count
```
