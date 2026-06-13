---
name: sql-query-optimization
description: |
  Query performance tuning, EXPLAIN plans, indexing strategies, and optimization techniques.
  Use this skill when queries are slow, you need to read execution plans, design indexes,
  write sargable predicates, optimize JOINs, implement partitioning, or maintain database
  statistics. Covers PostgreSQL, MySQL, and SQL Server optimization patterns.
---

# SQL Query Optimization

Essential patterns for diagnosing and fixing slow SQL queries across relational databases.

## Core Principles

1. **Measure before optimizing** - Always read the EXPLAIN plan before rewriting a query
2. **Indexes solve most problems** - 90% of slow queries are missing an appropriate index
3. **Keep predicates sargable** - Never wrap indexed columns in functions
4. **Reduce the working set early** - Filter and limit rows before joins and aggregations
5. **Statistics drive the optimizer** - Stale statistics produce bad plans regardless of indexes

## Reading EXPLAIN Plans

```sql
-- PostgreSQL: EXPLAIN ANALYZE shows actual execution times
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.order_id, c.customer_name, o.total_amount
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_date >= '2025-01-01'
  AND o.status = 'shipped';

-- Key output to examine:
-- Seq Scan on orders  (cost=0.00..18450.00 rows=5200 width=48) (actual time=0.03..112.5 rows=5180 loops=1)
--   Filter: ((order_date >= '2025-01-01') AND (status = 'shipped'))
--   Rows Removed by Filter: 994820
--   Buffers: shared hit=8450
-- Planning Time: 0.15 ms
-- Execution Time: 115.8 ms
```

See [explain-plan-reading.md](references/explain-plan-reading.md) for:
- EXPLAIN vs EXPLAIN ANALYZE differences and when to use each
- Understanding cost estimates, row counts, and width
- Identifying sequential scans, index scans, and bitmap scans
- Reading join algorithm nodes (Nested Loop, Hash Join, Merge Join)

## Index Selection and Design

```sql
-- Composite index: column order matters for range queries
-- Put equality columns first, range columns last
CREATE INDEX idx_orders_status_date
ON orders (status, order_date);

-- Covering index: includes all columns the query needs
-- Avoids heap table lookups entirely
CREATE INDEX idx_orders_covering
ON orders (status, order_date)
INCLUDE (customer_id, total_amount);

-- Partial index: smaller index, faster lookups
CREATE INDEX idx_orders_pending
ON orders (order_date)
WHERE status = 'pending';
```

See [index-optimization.md](references/index-optimization.md) for:
- When to create an index and when indexes hurt performance
- Composite index column ordering rules (equality-range-sort)
- Covering indexes with INCLUDE columns
- Partial and filtered indexes for selective queries

## Sargable Predicates

```sql
-- NON-SARGABLE: function wraps the indexed column, full table scan
SELECT * FROM orders
WHERE YEAR(order_date) = 2025 AND MONTH(order_date) = 6;

-- SARGABLE: direct comparison on indexed column, index seek
SELECT * FROM orders
WHERE order_date >= '2025-06-01'
  AND order_date < '2025-07-01';
```

See [sargable-queries.md](references/sargable-queries.md) for:
- Full list of sargable vs non-sargable predicate patterns
- Function-on-column traps and their rewrites
- Implicit type casting that prevents index usage
- LIKE prefix matching vs wildcard-leading patterns

## Query Rewriting Techniques

```sql
-- EXISTS is typically faster than IN for correlated checks on large tables
-- BAD: IN with subquery scans the full subquery result set
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id FROM orders o WHERE o.total_amount > 500
);

-- BETTER: EXISTS short-circuits on first match per row
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.total_amount > 500
);
```

See [query-rewriting.md](references/query-rewriting.md) for:
- EXISTS vs IN performance characteristics and NULL behavior
- CTE materialization fences and when CTEs hurt performance
- LATERAL joins for correlated subquery replacement
- Batch operations and row-at-a-time elimination

## JOIN Optimization

```sql
-- Let the optimizer choose the join algorithm, but understand the trade-offs
-- Nested Loop: best for small outer + indexed inner (< 1000 outer rows)
-- Hash Join: best for large unsorted sets with equality predicates
-- Merge Join: best when both sides are pre-sorted or indexed

-- Rewrite to reduce the working set BEFORE joining
WITH recent_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE order_date >= '2025-01-01'
)
SELECT c.customer_name, ro.total_amount
FROM recent_orders ro
JOIN customers c ON ro.customer_id = c.customer_id;
```

See [join-optimization.md](references/join-optimization.md) for:
- Join algorithm selection criteria and performance profiles
- Join order and how the optimizer chooses driving tables
- Statistics impact on join strategy selection
- Join hints and when to override the optimizer

## Table Partitioning

```sql
-- PostgreSQL: declarative range partitioning on a 500M-row table
CREATE TABLE events (
    event_id    BIGSERIAL,
    event_date  DATE NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB
) PARTITION BY RANGE (event_date);

CREATE TABLE events_2025_q1 PARTITION OF events
    FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
CREATE TABLE events_2025_q2 PARTITION OF events
    FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');

-- Queries that filter on event_date automatically prune partitions
SELECT * FROM events
WHERE event_date BETWEEN '2025-02-01' AND '2025-02-28';
-- Only scans events_2025_q1, skips all other partitions
```

See [partitioning-strategies.md](references/partitioning-strategies.md) for:
- Range, list, and hash partitioning use cases
- Partition pruning mechanics and verifying pruning in EXPLAIN
- Partition maintenance (adding, dropping, detaching)
- Sub-partitioning and composite partition keys

## Statistics Maintenance

```sql
-- PostgreSQL: manually refresh statistics after bulk loads
ANALYZE orders;
ANALYZE VERBOSE orders;  -- shows column-level stats gathered

-- Check when stats were last updated
SELECT
    schemaname, relname,
    last_analyze, last_autoanalyze,
    n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'orders';
```

See [statistics-maintenance.md](references/statistics-maintenance.md) for:
- ANALYZE (PostgreSQL) and UPDATE STATISTICS (SQL Server) usage
- Auto-vacuum thresholds and tuning parameters
- Histogram buckets and most-common-values lists
- Detecting stale statistics and cardinality misestimates

## Cross-Database Compatibility

| Feature | PostgreSQL | MySQL | SQL Server |
|---------|-----------|-------|------------|
| Execution plan | `EXPLAIN (ANALYZE, BUFFERS)` | `EXPLAIN ANALYZE` (8.0+) | `SET STATISTICS PROFILE ON` |
| Create index concurrently | `CREATE INDEX CONCURRENTLY` | `ALTER TABLE ... ALGORITHM=INPLACE` | `CREATE INDEX ... WITH (ONLINE=ON)` |
| Partial/filtered index | `WHERE clause` on index | Not supported | `WHERE clause` on index |
| Covering index | `INCLUDE (cols)` | Implicit (InnoDB secondary) | `INCLUDE (cols)` |
| Update statistics | `ANALYZE table` | `ANALYZE TABLE t` | `UPDATE STATISTICS t` |
| Partition pruning | Automatic (declarative) | Automatic | Automatic (partition elimination) |
| Index hints | `SET enable_seqscan=off` | `USE INDEX (idx)` | `WITH (INDEX(idx))` |
| Parallel query | Automatic (workers) | Limited (8.0+) | `MAXDOP` hint |

## Anti-Patterns to Avoid

| Avoid | Use Instead | Why |
|-------|-------------|-----|
| `SELECT *` in production queries | Explicit column list | Prevents covering index usage, transfers excess data |
| `WHERE UPPER(email) = 'FOO'` | Expression index or `citext` type | Wrapping column in function prevents index seek |
| `ORDER BY RAND()` for random rows | `TABLESAMPLE` or offset-based random | Full table scan and sort on every execution |
| Correlated subquery in SELECT list | JOIN with aggregation | Executes subquery once per outer row (N+1 problem) |
| `NOT IN (subquery)` with NULLs | `NOT EXISTS` or `LEFT JOIN WHERE NULL` | NULL in subquery makes entire predicate UNKNOWN |
| Index on every column | Targeted composite indexes | Write overhead, storage waste, optimizer confusion |
| `OFFSET 10000 ROWS` for deep paging | Keyset pagination (`WHERE id > last_seen`) | Offset still scans and discards skipped rows |
| Hint-driven query plans | Fix statistics and indexes first | Hints become stale as data distribution changes |

## Performance Benchmarking

- Always test with production-scale data; plans change dramatically at different row counts
- Compare `Seq Scan` cost vs `Index Scan` cost in EXPLAIN output
- Watch for "Rows Removed by Filter" -- a high number signals a missing or wrong index
- Monitor `shared hit` vs `shared read` in BUFFERS output to gauge cache effectiveness
- Use `pg_stat_statements` (PostgreSQL) or Query Store (SQL Server) to track slow queries over time
- Re-ANALYZE after bulk loads, schema changes, or large DELETE operations

source: PostgreSQL docs, MySQL optimization guide, SQL Server Query Processing Architecture, Use The Index Luke (Markus Winand)
