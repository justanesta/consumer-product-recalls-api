# JOIN Optimization

Guide to understanding join algorithms, controlling join order, and tuning join performance across databases.

## Join Algorithm Overview

Relational databases use three core join algorithms. The optimizer selects the best one based on table sizes, available indexes, sort order, and statistics.

| Algorithm | Best When | Memory | Index Required |
|-----------|----------|--------|----------------|
| Nested Loop | Small outer set + indexed inner | Low | Yes (inner side) |
| Hash Join | Large unsorted sets, equality join | High (hash table) | No |
| Merge Join | Both sides pre-sorted or indexed | Moderate | Beneficial |

## Nested Loop Join

The optimizer drives from the outer (smaller) table and looks up each row in the inner table via an index. Total cost is proportional to `outer_rows * index_lookup_cost`.

```sql
-- Ideal for nested loop: 14 outer rows, indexed inner lookup
EXPLAIN ANALYZE
SELECT o.order_id, li.product_id, li.quantity
FROM orders o
JOIN line_items li ON li.order_id = o.order_id
WHERE o.customer_id = 42;

-- Nested Loop  (actual time=0.04..0.52 rows=58 loops=1)
--   -> Index Scan using idx_orders_customer on orders o
--        (actual time=0.02..0.05 rows=14 loops=1)
--        Index Cond: (customer_id = 42)
--   -> Index Scan using idx_li_order_id on line_items li
--        (actual time=0.01..0.03 rows=4 loops=14)
--        Index Cond: (order_id = o.order_id)
-- Total: 14 outer rows * 4 avg inner rows = 56 result rows
```

**When nested loop becomes slow:**
- Outer table returns thousands of rows -- each one triggers an inner index lookup
- Inner table has no index on the join column -- falls back to sequential scan per loop
- Fix: ensure the inner table has an index on the join column, or reduce the outer set with tighter filters

```sql
-- BAD: 100K outer rows with nested loop into unindexed inner
-- Fix: create the missing index
CREATE INDEX idx_line_items_order_id ON line_items (order_id);
```

## Hash Join

Builds an in-memory hash table from the smaller (build) side, then probes it with each row from the larger (probe) side. Requires equality join conditions.

```sql
-- Hash join: 50K filtered orders as build side, 1M line_items as probe
EXPLAIN ANALYZE
SELECT o.order_id, o.order_date, li.product_id, li.quantity
FROM orders o
JOIN line_items li ON li.order_id = o.order_id
WHERE o.order_date >= '2025-01-01';

-- Hash Join  (actual time=42.1..310.5 rows=196400 loops=1)
--   Hash Cond: (li.order_id = o.order_id)
--   -> Seq Scan on line_items li  (rows=1000000)
--   -> Hash  (rows=52400)
--        Buckets: 65536  Batches: 1  Memory Usage: 2840kB
--        -> Seq Scan on orders o (filtered by date)
```

**Performance considerations:**
- **Batches: 1** means the entire hash table fits in `work_mem` -- optimal
- **Batches > 1** means the hash table spilled to disk -- increase `work_mem`
- Hash joins do not require indexes on either side
- Hash joins only work with equality predicates (`=`), not range predicates

```sql
-- PostgreSQL: increase work_mem for a session with large hash joins
SET work_mem = '256MB';
-- Only for the current session; resets on disconnect

-- SQL Server: use a memory grant hint if the optimizer underestimates
SELECT o.order_id, li.product_id
FROM orders o
JOIN line_items li ON li.order_id = o.order_id
OPTION (MIN_GRANT_PERCENT = 10);
```

## Merge Join

Both inputs must be sorted on the join key. The algorithm walks through both sorted streams simultaneously. Efficient when both sides are already sorted (e.g., from index scans) or when the data is large enough that sorting + merge is cheaper than hashing.

```sql
-- Merge join: both sides sorted via index scans on customer_id
EXPLAIN ANALYZE
SELECT c.customer_name, o.order_id, o.total_amount
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id;

-- Merge Join  (actual time=0.04..450.2 rows=998500 loops=1)
--   Merge Cond: (c.customer_id = o.customer_id)
--   -> Index Scan using customers_pkey on customers c
--   -> Index Scan using idx_orders_customer on orders o
```

If no index provides the sort order, the optimizer adds an explicit Sort node before the merge, which may spill to disk for large tables.

## Join Order Optimization

The optimizer evaluates different join orders to find the cheapest plan. For queries joining many tables, this becomes critical.

```sql
-- 5-table join: optimizer tries various orderings
SELECT
    c.customer_name,
    o.order_id,
    p.product_name,
    s.supplier_name,
    w.warehouse_location
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN line_items li ON li.order_id = o.order_id
JOIN products p ON p.product_id = li.product_id
JOIN suppliers s ON s.supplier_id = p.supplier_id
JOIN warehouses w ON w.warehouse_id = li.warehouse_id
WHERE c.region = 'US-West'
  AND o.order_date >= '2025-01-01';
```

**How the optimizer decides join order:**
1. Estimates the selectivity of each WHERE filter
2. Starts with the table that produces the fewest rows after filtering
3. Joins the next table that produces the smallest intermediate result
4. Accurate statistics are essential for correct join order decisions

```sql
-- PostgreSQL: check how many join orderings the optimizer considers
SHOW join_collapse_limit;    -- default 8 (considers all orderings for <= 8 tables)
SHOW from_collapse_limit;    -- default 8

-- For queries with > 8 tables, the optimizer uses heuristics (GEQO)
-- which may miss the optimal plan
-- Temporarily increase for critical queries:
SET join_collapse_limit = 12;
```

## Reducing Working Set Before Joins

Filter and aggregate early to reduce the number of rows entering expensive joins.

```sql
-- SLOW: join 1M orders to 5M line_items, then filter
SELECT c.customer_name, SUM(li.quantity * li.unit_price) AS total
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN line_items li ON li.order_id = o.order_id
WHERE o.order_date >= '2025-06-01'
GROUP BY c.customer_name;

-- FASTER: pre-filter orders, pre-aggregate line items
WITH recent_orders AS (
    SELECT order_id, customer_id
    FROM orders
    WHERE order_date >= '2025-06-01'
),
order_totals AS (
    SELECT li.order_id, SUM(li.quantity * li.unit_price) AS order_total
    FROM line_items li
    JOIN recent_orders ro ON li.order_id = ro.order_id
    GROUP BY li.order_id
)
SELECT c.customer_name, SUM(ot.order_total) AS total
FROM customers c
JOIN recent_orders ro ON ro.customer_id = c.customer_id
JOIN order_totals ot ON ot.order_id = ro.order_id
GROUP BY c.customer_name;
```

Note: modern optimizers often push predicates down automatically. Verify with EXPLAIN before rewriting -- the CTE approach may not always be faster.

## Join Hints (Use Sparingly)

Override the optimizer's join algorithm or order choice. Use only when statistics are accurate but the optimizer still picks a bad plan.

```sql
-- PostgreSQL: disable specific join types to force alternatives
SET enable_hashjoin = off;   -- forces nested loop or merge join
SET enable_nestloop = off;   -- forces hash or merge join
SET enable_mergejoin = off;  -- forces hash or nested loop
-- Reset after the query:
RESET enable_hashjoin;

-- MySQL: STRAIGHT_JOIN forces left-to-right join order
SELECT STRAIGHT_JOIN c.customer_name, o.order_id
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id;

-- MySQL: join algorithm hints
SELECT /*+ HASH_JOIN(o, li) */ o.order_id, li.product_id
FROM orders o
JOIN line_items li ON li.order_id = o.order_id;

-- SQL Server: join hints
SELECT c.customer_name, o.order_id
FROM customers c
INNER HASH JOIN orders o ON o.customer_id = c.customer_id;

-- SQL Server: force join order
SELECT c.customer_name, o.order_id
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
OPTION (FORCE ORDER);
```

**Why hints are dangerous:**
- They bypass the optimizer, which means they ignore future data distribution changes
- A hint that helps today may hurt after a bulk load changes table sizes
- Always prefer fixing statistics, adding indexes, or rewriting the query first

## Anti-Patterns in JOINs

```sql
-- ANTI-PATTERN: function in JOIN condition prevents index usage
SELECT *
FROM orders o
JOIN customers c ON LOWER(c.email) = LOWER(o.contact_email);
-- Fix: normalize data at write time, or use expression indexes

-- ANTI-PATTERN: implicit cross join (missing join condition)
SELECT * FROM orders o, line_items li;  -- Cartesian product!
-- Fix: always use explicit JOIN ... ON

-- ANTI-PATTERN: OR in join condition
SELECT *
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
                 OR c.email = o.contact_email;
-- Fix: split into two queries with UNION

-- ANTI-PATTERN: joining on non-indexed columns in large tables
SELECT * FROM table_a a
JOIN table_b b ON a.unindexed_col = b.unindexed_col;
-- Fix: create indexes on both join columns
CREATE INDEX idx_a_col ON table_a (unindexed_col);
CREATE INDEX idx_b_col ON table_b (unindexed_col);
```

## Monitoring Join Performance

```sql
-- PostgreSQL: identify slow joins by examining actual vs estimated rows
EXPLAIN (ANALYZE, BUFFERS)
SELECT ... FROM a JOIN b ON ...;

-- Look for:
-- 1. "rows=1000" estimated but "actual rows=500000" -> stale statistics
-- 2. "Nested Loop" with loops=100000 -> consider hash join
-- 3. "Hash Batches: 4" -> hash spilling to disk, increase work_mem
-- 4. "Sort Method: external merge" -> sort spilling, increase work_mem

-- PostgreSQL: track join performance over time
SELECT query, calls, mean_exec_time, rows
FROM pg_stat_statements
WHERE query LIKE '%JOIN%'
ORDER BY mean_exec_time DESC
LIMIT 20;
```
