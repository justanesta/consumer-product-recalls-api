# Index Optimization

Comprehensive guide to designing, creating, and maintaining indexes for query performance.

## When to Create an Index

Create an index when:
- A column appears frequently in WHERE, JOIN ON, or ORDER BY clauses
- The column has high selectivity (many distinct values relative to total rows)
- The query returns a small fraction of the table (typically < 10-15%)
- EXPLAIN shows a Seq Scan on a large table with few rows returned

Do NOT create an index when:
- The table is small (< 10K rows) -- sequential scan is often faster
- The column has very low cardinality (e.g., boolean, status with 3 values)
- The table is write-heavy and rarely queried
- The query already returns most rows in the table

```sql
-- Check column selectivity before indexing
SELECT
    COUNT(DISTINCT customer_id) AS distinct_values,
    COUNT(*) AS total_rows,
    ROUND(COUNT(DISTINCT customer_id)::NUMERIC / COUNT(*), 4) AS selectivity
FROM orders;
-- selectivity = 0.05 means 5% unique -> good index candidate for point lookups
-- selectivity = 0.0001 means very few distinct values -> poor candidate alone
```

## Composite Index Column Ordering

The column order in a composite index determines which queries it can serve. Follow the **equality-range-sort** rule:

1. **Equality columns first** -- columns compared with `=`
2. **Range columns next** -- columns compared with `>`, `<`, `BETWEEN`, `IN`
3. **Sort columns last** -- columns in ORDER BY

```sql
-- Query pattern:
SELECT order_id, total_amount
FROM orders
WHERE status = 'shipped'          -- equality
  AND order_date >= '2025-01-01'  -- range
ORDER BY total_amount DESC;       -- sort

-- Optimal composite index:
CREATE INDEX idx_orders_status_date_amount
ON orders (status, order_date, total_amount);
```

**Why order matters:**

```sql
-- Index on (status, order_date) serves these queries:
WHERE status = 'shipped'                              -- YES (leftmost prefix)
WHERE status = 'shipped' AND order_date >= '2025-01-01' -- YES (both columns)
WHERE order_date >= '2025-01-01'                      -- NO (skips leftmost column)

-- The index is a sorted tree: status first, then order_date within each status
-- Skipping the leftmost column means the index cannot narrow the search
```

## Covering Indexes with INCLUDE

A covering index contains all columns a query references, eliminating the need to fetch the full row from the heap table. This turns an Index Scan into an Index Only Scan.

```sql
-- Query that needs customer_id and total_amount in the result
SELECT customer_id, total_amount
FROM orders
WHERE status = 'shipped' AND order_date >= '2025-01-01';

-- Without INCLUDE: Index Scan (finds rows via index, then fetches heap for customer_id, total_amount)
CREATE INDEX idx_orders_status_date
ON orders (status, order_date);

-- With INCLUDE: Index Only Scan (no heap fetch needed)
CREATE INDEX idx_orders_covering
ON orders (status, order_date)
INCLUDE (customer_id, total_amount);
```

**INCLUDE vs adding columns to the index key:**
- INCLUDE columns are stored in leaf pages only, not in the B-tree internal nodes
- INCLUDE columns do not affect sort order or searchability
- INCLUDE columns reduce index size compared to adding them as key columns
- Use INCLUDE for columns that appear only in SELECT, not in WHERE or ORDER BY

```sql
-- PostgreSQL and SQL Server support INCLUDE
CREATE INDEX idx_covering ON orders (status) INCLUDE (customer_id, total_amount);

-- MySQL InnoDB: secondary indexes implicitly include the primary key
-- All secondary index leaf nodes store the PK, so the PK columns are always "included"
```

## Partial (Filtered) Indexes

A partial index covers only rows matching a WHERE predicate. Useful when queries consistently filter on a specific condition.

```sql
-- Only 2% of orders are 'pending', but they are queried frequently
CREATE INDEX idx_orders_pending
ON orders (order_date, customer_id)
WHERE status = 'pending';

-- This index is:
-- 1. ~50x smaller than a full index (only 2% of rows)
-- 2. Faster to scan and maintain
-- 3. Used only when the query includes WHERE status = 'pending'
```

```sql
-- PostgreSQL: partial index
CREATE INDEX idx_active_users ON users (email) WHERE is_active = true;

-- SQL Server: filtered index
CREATE INDEX idx_active_users ON users (email) WHERE is_active = 1;

-- MySQL: does not support partial/filtered indexes
-- Workaround: add the filter column to the composite index
CREATE INDEX idx_users_active_email ON users (is_active, email);
```

## Expression Indexes

When queries consistently apply a function to a column, create an index on the expression.

```sql
-- Query uses LOWER(email) for case-insensitive lookup
SELECT * FROM users WHERE LOWER(email) = 'john@example.com';

-- Without expression index: Seq Scan (function prevents index usage)
-- With expression index: Index Scan
CREATE INDEX idx_users_lower_email ON users (LOWER(email));

-- PostgreSQL alternative: use citext extension for case-insensitive text
-- CREATE EXTENSION citext;
-- ALTER TABLE users ALTER COLUMN email TYPE citext;
```

```sql
-- Index on date extraction for date-grouped queries
CREATE INDEX idx_orders_year_month
ON orders (DATE_TRUNC('month', order_date));

-- Now this query uses the index:
SELECT DATE_TRUNC('month', order_date) AS month, COUNT(*)
FROM orders
GROUP BY DATE_TRUNC('month', order_date);
```

## Index Types Beyond B-Tree

```sql
-- Hash index: equality-only lookups, smaller than B-tree (PostgreSQL 10+)
CREATE INDEX idx_orders_hash_status ON orders USING HASH (status);
-- Only supports = operator, not range queries

-- GIN index: full-text search and array/JSONB containment (PostgreSQL)
CREATE INDEX idx_products_tags ON products USING GIN (tags);
SELECT * FROM products WHERE tags @> ARRAY['electronics', 'sale'];

-- GiST index: geometric, range, and proximity queries (PostgreSQL)
CREATE INDEX idx_locations_point ON locations USING GIST (coordinates);

-- BRIN index: very compact, for naturally ordered large tables (PostgreSQL)
-- Ideal for append-only tables with correlated physical and logical order
CREATE INDEX idx_events_date_brin ON events USING BRIN (event_date);
-- Stores min/max per block range; extremely small but less precise
```

## Monitoring Index Usage

```sql
-- PostgreSQL: find unused indexes
SELECT
    schemaname, relname AS table_name,
    indexrelname AS index_name,
    idx_scan AS times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- PostgreSQL: find missing indexes (tables with high seq scan counts)
SELECT
    relname AS table_name,
    seq_scan, idx_scan,
    seq_tup_read, idx_tup_fetch,
    ROUND(100.0 * idx_scan / NULLIF(seq_scan + idx_scan, 0), 1) AS idx_scan_pct
FROM pg_stat_user_tables
WHERE seq_scan > 100
ORDER BY seq_tup_read DESC
LIMIT 20;
```

## Creating Indexes Without Downtime

```sql
-- PostgreSQL: CONCURRENTLY avoids locking the table for writes
CREATE INDEX CONCURRENTLY idx_orders_date ON orders (order_date);
-- Takes longer but does not block INSERT/UPDATE/DELETE
-- If it fails, you get an INVALID index; drop and retry

-- SQL Server: ONLINE option
CREATE INDEX idx_orders_date ON orders (order_date) WITH (ONLINE = ON);

-- MySQL InnoDB: most ALTER TABLE ... ADD INDEX operations are online by default in 5.6+
ALTER TABLE orders ADD INDEX idx_orders_date (order_date), ALGORITHM=INPLACE, LOCK=NONE;
```

## Index Maintenance

```sql
-- PostgreSQL: check index bloat
SELECT
    indexrelname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- PostgreSQL: rebuild a bloated index without downtime
REINDEX INDEX CONCURRENTLY idx_orders_date;

-- SQL Server: rebuild or reorganize
ALTER INDEX idx_orders_date ON orders REBUILD;       -- full rebuild, locks table
ALTER INDEX idx_orders_date ON orders REORGANIZE;    -- online defrag, no lock
```

## Common Index Mistakes

1. **Indexing every column individually** -- Composite indexes serve multi-column queries; single-column indexes often go unused
2. **Wrong column order in composite index** -- Leftmost prefix rule means order determines usability
3. **Ignoring INCLUDE for covering queries** -- Forces unnecessary heap lookups
4. **Never removing unused indexes** -- Each index slows down writes and consumes storage
5. **Duplicating the primary key in secondary indexes** -- InnoDB already includes PK in all secondary indexes
6. **Creating indexes before understanding query patterns** -- Profile first, index second
