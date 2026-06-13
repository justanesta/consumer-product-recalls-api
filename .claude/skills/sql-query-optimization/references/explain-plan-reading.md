# Reading EXPLAIN Plans

Comprehensive guide to interpreting query execution plans across PostgreSQL, MySQL, and SQL Server.

## EXPLAIN vs EXPLAIN ANALYZE

EXPLAIN shows the **planned** execution path without running the query. EXPLAIN ANALYZE actually **executes** the query and shows real timing and row counts alongside the estimates.

```sql
-- PostgreSQL: plan only (safe for expensive queries)
EXPLAIN
SELECT * FROM orders WHERE customer_id = 42;

-- PostgreSQL: plan + actual execution (runs the query!)
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 42;

-- MySQL: basic plan
EXPLAIN SELECT * FROM orders WHERE customer_id = 42;

-- MySQL 8.0+: actual execution stats
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = 42;

-- SQL Server: estimated plan
SET SHOWPLAN_XML ON;
GO
SELECT * FROM orders WHERE customer_id = 42;
GO
SET SHOWPLAN_XML OFF;

-- SQL Server: actual plan
SET STATISTICS PROFILE ON;
SELECT * FROM orders WHERE customer_id = 42;
SET STATISTICS PROFILE OFF;
```

**When to use each:**
- Use `EXPLAIN` when the query modifies data or takes minutes to run
- Use `EXPLAIN ANALYZE` when you need to compare estimated vs actual row counts
- Large discrepancies between estimated and actual rows indicate stale statistics

## Understanding Cost Estimates

PostgreSQL costs are in arbitrary units relative to `seq_page_cost = 1.0`:

```sql
EXPLAIN SELECT * FROM orders WHERE order_date >= '2025-01-01';
-- Seq Scan on orders  (cost=0.00..21370.00 rows=52400 width=96)
--   Filter: (order_date >= '2025-01-01')
```

Breaking down the output:
- **cost=0.00..21370.00** -- startup cost (before first row) .. total cost (all rows)
- **rows=52400** -- estimated number of rows returned
- **width=96** -- estimated average row size in bytes

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE order_date >= '2025-01-01';
-- Seq Scan on orders  (cost=0.00..21370.00 rows=52400 width=96)
--                      (actual time=0.02..98.7 rows=51830 loops=1)
--   Filter: (order_date >= '2025-01-01')
--   Rows Removed by Filter: 948170
--   Buffers: shared hit=11370
-- Planning Time: 0.12 ms
-- Execution Time: 105.4 ms
```

Key actual-time fields:
- **actual time=0.02..98.7** -- time to first row .. time to last row (ms)
- **rows=51830** -- actual rows returned (compare to estimated 52400)
- **loops=1** -- how many times this node executed (important for nested loops)
- **Rows Removed by Filter: 948170** -- rows scanned but discarded (red flag if high)
- **Buffers: shared hit=11370** -- pages read from shared buffer cache

## Scan Types

### Sequential Scan (Seq Scan)
Reads every page of the table. Expected for small tables or queries returning a large percentage of rows.

```sql
-- Full table scan: reading 1M rows to find 800K matches
EXPLAIN ANALYZE
SELECT * FROM orders WHERE status IN ('shipped', 'delivered', 'returned');
-- Seq Scan on orders  (cost=0.00..24370.00 rows=812000 width=96)
--                      (actual time=0.01..142.3 rows=810450 loops=1)
```

### Index Scan
Uses the index B-tree to find matching rows, then fetches the full row from the heap table.

```sql
-- Index scan: uses idx_orders_customer_id to find 15 rows
EXPLAIN ANALYZE
SELECT * FROM orders WHERE customer_id = 42;
-- Index Scan using idx_orders_customer_id on orders
--   (cost=0.43..58.20 rows=15 width=96) (actual time=0.02..0.08 rows=14 loops=1)
--   Index Cond: (customer_id = 42)
```

### Index Only Scan
All requested columns are in the index; no heap fetch needed. This is the fastest scan type.

```sql
-- Covering index: CREATE INDEX idx_cov ON orders (customer_id) INCLUDE (order_date, total_amount)
EXPLAIN ANALYZE
SELECT customer_id, order_date, total_amount FROM orders WHERE customer_id = 42;
-- Index Only Scan using idx_cov on orders
--   (cost=0.43..12.60 rows=15 width=20) (actual time=0.01..0.03 rows=14 loops=1)
--   Heap Fetches: 0
```

### Bitmap Index Scan + Bitmap Heap Scan
Used when an index scan would visit too many scattered heap pages. Builds a bitmap of matching pages first, then reads them in sequential order.

```sql
-- Bitmap scan: too many matches for a plain index scan, too few for seq scan
EXPLAIN ANALYZE
SELECT * FROM orders WHERE order_date BETWEEN '2025-01-01' AND '2025-03-31';
-- Bitmap Heap Scan on orders  (cost=520.00..12450.00 rows=24800 width=96)
--   Recheck Cond: (order_date >= '2025-01-01' AND order_date < '2025-04-01')
--   -> Bitmap Index Scan on idx_orders_date  (cost=0.00..514.00 rows=24800 width=0)
```

## Join Algorithm Nodes

### Nested Loop Join
Best for small outer result sets with an indexed lookup on the inner table.

```sql
-- Small outer (14 rows from customer 42) nested-loop into line_items via index
EXPLAIN ANALYZE
SELECT o.order_id, li.product_id, li.quantity
FROM orders o
JOIN line_items li ON li.order_id = o.order_id
WHERE o.customer_id = 42;

-- Nested Loop  (cost=0.86..245.00 rows=60 width=16)
--              (actual time=0.04..0.52 rows=58 loops=1)
--   -> Index Scan using idx_orders_customer on orders o
--        (actual time=0.02..0.05 rows=14 loops=1)
--   -> Index Scan using idx_li_order_id on line_items li
--        (actual time=0.01..0.03 rows=4 loops=14)
```

Note `loops=14` on the inner scan: it executes once per outer row.

### Hash Join
Builds an in-memory hash table from the smaller side, probes it with the larger side. Best for large unsorted sets.

```sql
-- Hash join: 50K orders hashed, 1M line_items probed
EXPLAIN ANALYZE
SELECT o.order_id, o.order_date, li.product_id
FROM orders o
JOIN line_items li ON li.order_id = o.order_id
WHERE o.order_date >= '2025-01-01';

-- Hash Join  (cost=1850.00..45200.00 rows=198000 width=20)
--            (actual time=42.1..310.5 rows=196400 loops=1)
--   Hash Cond: (li.order_id = o.order_id)
--   -> Seq Scan on line_items li  (cost=0.00..28500.00 rows=1000000 width=12)
--   -> Hash  (cost=1350.00..1350.00 rows=52400 width=12)
--        Buckets: 65536  Batches: 1  Memory Usage: 2840kB
--        -> Seq Scan on orders o (filtering by date)
```

**Batches > 1** means the hash table spilled to disk -- a performance warning.

### Merge Join
Requires both inputs sorted on the join key. Efficient for large pre-sorted data sets.

```sql
-- Merge join: both sides sorted on customer_id via indexes
EXPLAIN ANALYZE
SELECT c.customer_name, o.order_id
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id;

-- Merge Join  (cost=0.86..52000.00 rows=1000000 width=28)
--             (actual time=0.04..450.2 rows=998500 loops=1)
--   Merge Cond: (c.customer_id = o.customer_id)
--   -> Index Scan using customers_pkey on customers c
--   -> Index Scan using idx_orders_customer on orders o
```

## Common Red Flags in EXPLAIN Output

1. **Rows Removed by Filter >> rows returned** -- Missing index on filter column
2. **Estimated rows far from actual rows** -- Stale statistics, run ANALYZE
3. **Nested Loop with high loops count and Seq Scan inner** -- Missing index on join column
4. **Sort with external merge** -- `work_mem` too low, sort spilling to disk
5. **Hash Batches > 1** -- `work_mem` too low for hash join, spilling to disk
6. **Seq Scan on large table with small result set** -- Missing or unused index

## PostgreSQL EXPLAIN Format Options

```sql
-- TEXT format (default, human-readable)
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT ...;

-- JSON format (machine-parseable, includes detailed timing)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT ...;

-- Use explain.dalibo.com to visualize JSON plans interactively
```

## Analyzing Subquery and CTE Plans

```sql
-- CTE materializes into a temp structure (look for "CTE Scan" node)
EXPLAIN ANALYZE
WITH active_customers AS (
    SELECT customer_id FROM customers WHERE status = 'active'
)
SELECT o.* FROM orders o
JOIN active_customers ac ON o.customer_id = ac.customer_id;

-- CTE Scan on active_customers  (cost=0.00..1200.00 rows=60000 width=4)
-- This means the CTE result was fully materialized before the join
```

In PostgreSQL 12+, simple CTEs may be inlined (not materialized). Use `MATERIALIZED` or `NOT MATERIALIZED` to control this explicitly.

## Tips for Efficient Plan Reading

- Read the plan from the innermost indented node outward
- Multiply `actual time` by `loops` for true cost of nested nodes
- Compare `rows` (estimated) vs `actual rows` at every node to spot statistics drift
- Use `BUFFERS` output to distinguish cached reads (shared hit) from disk reads (shared read)
- After adding an index, re-run EXPLAIN ANALYZE to confirm the planner uses it
