# Index Design Patterns

## B-Tree Indexes (Default)

The standard index type in all major databases. Supports equality (`=`) and range (`<`, `>`, `BETWEEN`) queries.

```sql
-- Single column index for equality lookups
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- Single column index for range queries
CREATE INDEX idx_orders_date ON orders(order_date);

-- These queries benefit from the indexes above:
-- SELECT * FROM orders WHERE customer_id = 12345;
-- SELECT * FROM orders WHERE order_date BETWEEN '2024-01-01' AND '2024-03-31';
-- SELECT * FROM orders WHERE order_date >= '2024-01-01' ORDER BY order_date;
```

## Composite (Multi-Column) Indexes

### Column Order Matters

The leftmost columns in a composite index are the most important. The index supports queries that filter on a **left prefix** of the index columns.

```sql
CREATE INDEX idx_orders_cust_date ON orders(customer_id, order_date);

-- USES the index (filters on leftmost column):
SELECT * FROM orders WHERE customer_id = 12345;
SELECT * FROM orders WHERE customer_id = 12345 AND order_date >= '2024-01-01';
SELECT * FROM orders WHERE customer_id = 12345 ORDER BY order_date;

-- DOES NOT use this index effectively (skips leftmost column):
SELECT * FROM orders WHERE order_date = '2024-03-15';
-- For this query, you need a separate index on (order_date)
```

### Column Order Strategy

```sql
-- Rule of thumb: equality columns first, then range columns, then sort columns

-- Query: WHERE status = 'active' AND created_at > '2024-01-01' ORDER BY priority
CREATE INDEX idx_tasks_status_created_priority
    ON tasks(status, created_at, priority);
-- status: equality (goes first)
-- created_at: range (goes second)
-- priority: sort (goes last)

-- High-cardinality columns generally go before low-cardinality
-- Exception: if a low-cardinality column is always in the WHERE clause, put it first

-- Common pattern: composite index matching a frequent query
-- Query: SELECT * FROM products WHERE category_id = ? AND status = 'active' ORDER BY price;
CREATE INDEX idx_products_cat_status_price ON products(category_id, status, price);
```

## Covering Indexes (Index-Only Scans)

Include extra columns so the query can be answered entirely from the index without touching the table.

```sql
-- PostgreSQL: INCLUDE clause (non-searchable columns stored in the index)
CREATE INDEX idx_orders_covering ON orders(customer_id, order_date)
    INCLUDE (total_amount, status);

-- This query can be satisfied from the index alone (index-only scan):
SELECT customer_id, order_date, total_amount, status
FROM orders
WHERE customer_id = 12345
  AND order_date >= '2024-01-01';
-- No need to read the actual table rows

-- SQL Server: equivalent INCLUDE syntax
CREATE INDEX idx_orders_covering ON orders(customer_id, order_date)
    INCLUDE (total_amount, status);

-- MySQL: no INCLUDE keyword, but you can add columns to the index itself
CREATE INDEX idx_orders_covering ON orders(customer_id, order_date, total_amount, status);
-- All columns are searchable in MySQL (no distinction between key and included)
```

## Partial Indexes (Filtered Indexes)

Index only rows that match a condition. Smaller, faster, and more targeted.

```sql
-- PostgreSQL: partial index
CREATE INDEX idx_active_orders ON orders(customer_id, order_date)
    WHERE status = 'active';
-- Much smaller than indexing all orders if most are 'completed' or 'cancelled'

-- Only index non-null values (skip sparse columns)
CREATE INDEX idx_orders_tracking ON orders(tracking_number)
    WHERE tracking_number IS NOT NULL;

-- SQL Server: filtered index
CREATE INDEX idx_active_orders ON orders(customer_id, order_date)
    WHERE status = 'active';

-- Practical example: unique constraint only for active records
CREATE UNIQUE INDEX uq_active_subscription ON subscriptions(customer_id)
    WHERE status = 'active';
-- Allows multiple cancelled subscriptions but only one active per customer
```

## GIN Indexes (Generalized Inverted Index)

Best for multi-valued data: arrays, JSONB, full-text search (PostgreSQL).

```sql
-- JSONB column indexing
CREATE INDEX idx_products_attrs ON products USING gin(attributes);

-- Enables fast queries on JSONB:
SELECT * FROM products WHERE attributes @> '{"color": "red"}';
SELECT * FROM products WHERE attributes ? 'wireless';

-- Array column indexing
CREATE INDEX idx_articles_tags ON articles USING gin(tags);

-- Enables array containment queries:
SELECT * FROM articles WHERE tags @> ARRAY['sql', 'performance'];
SELECT * FROM articles WHERE 'postgresql' = ANY(tags);

-- Full-text search
CREATE INDEX idx_articles_fts ON articles USING gin(to_tsvector('english', title || ' ' || body));

-- Query with full-text search:
SELECT * FROM articles
WHERE to_tsvector('english', title || ' ' || body) @@ to_tsquery('english', 'database & performance');
```

## GiST Indexes (Generalized Search Tree)

Best for geometric data, range types, and nearest-neighbor queries (PostgreSQL).

```sql
-- Range type overlap queries
CREATE INDEX idx_bookings_timerange ON room_bookings USING gist(
    tstzrange(start_time, end_time)
);

-- Find overlapping bookings:
SELECT * FROM room_bookings
WHERE tstzrange(start_time, end_time) && tstzrange('2024-03-15 09:00', '2024-03-15 17:00');

-- Geographic data (with PostGIS)
CREATE INDEX idx_stores_location ON stores USING gist(location);

-- Find nearest stores:
SELECT store_name, ST_Distance(location, ST_MakePoint(-122.4194, 37.7749)) AS distance_m
FROM stores
ORDER BY location <-> ST_MakePoint(-122.4194, 37.7749)
LIMIT 10;
```

## Expression Indexes

Index on a computed expression rather than a raw column.

```sql
-- Index on lowercased email for case-insensitive lookups
CREATE INDEX idx_users_email_lower ON users(LOWER(email));

-- Query must use the same expression:
SELECT * FROM users WHERE LOWER(email) = 'jane@example.com';

-- Index on date part for year-based queries
CREATE INDEX idx_orders_year ON orders(EXTRACT(YEAR FROM order_date));

-- Index on JSON field
CREATE INDEX idx_config_env ON app_config((config->>'environment'));
SELECT * FROM app_config WHERE config->>'environment' = 'production';
```

## Index Strategies by Query Pattern

| Query Pattern | Recommended Index |
|---------------|-------------------|
| `WHERE col = value` | B-tree on `col` |
| `WHERE col1 = ? AND col2 = ?` | Composite B-tree on `(col1, col2)` |
| `WHERE col BETWEEN a AND b` | B-tree on `col` |
| `WHERE col = ? ORDER BY col2` | Composite B-tree on `(col, col2)` |
| `WHERE LOWER(col) = ?` | Expression index on `LOWER(col)` |
| `WHERE jsonb_col @> '{...}'` | GIN on `jsonb_col` |
| `WHERE array_col @> ARRAY[...]` | GIN on `array_col` |
| `WHERE status = 'active'` (rare status) | Partial index `WHERE status = 'active'` |
| `SELECT a, b FROM t WHERE a = ?` | Covering index on `(a) INCLUDE (b)` |
| Range overlap / spatial | GiST |

## When NOT to Index

```sql
-- Small tables (under ~10,000 rows): full scan is often faster than index lookup
-- Columns with very low cardinality on large tables (e.g., boolean status with 50/50 split)
-- Tables that are write-heavy with few reads
-- Columns that are rarely used in WHERE, JOIN, or ORDER BY

-- Too many indexes slow down writes:
-- Each INSERT/UPDATE/DELETE must maintain all indexes on the table
-- Monitor unused indexes:
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan AS times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

## Index Maintenance

```sql
-- Check index bloat (PostgreSQL)
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size,
    idx_scan AS scans,
    idx_tup_read AS tuples_read,
    idx_tup_fetch AS tuples_fetched
FROM pg_stat_user_indexes
JOIN pg_indexes USING (schemaname, tablename, indexname)
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexname::regclass) DESC;

-- Rebuild bloated indexes (PostgreSQL, non-blocking)
REINDEX INDEX CONCURRENTLY idx_orders_customer_id;

-- Rebuild all indexes on a table
REINDEX TABLE CONCURRENTLY orders;

-- Update statistics for the query planner
ANALYZE orders;
```

## Index Anti-Patterns

```sql
-- BAD: Indexing every column individually
CREATE INDEX idx1 ON orders(customer_id);
CREATE INDEX idx2 ON orders(order_date);
CREATE INDEX idx3 ON orders(status);
CREATE INDEX idx4 ON orders(total_amount);
-- For a query with WHERE customer_id = ? AND status = ?, the database
-- might only use one of these. A composite index is better.

-- GOOD: One composite index for the common query pattern
CREATE INDEX idx_orders_cust_status ON orders(customer_id, status);

-- BAD: Redundant indexes
CREATE INDEX idx_a ON orders(customer_id);
CREATE INDEX idx_b ON orders(customer_id, order_date);
-- idx_a is redundant because idx_b covers single-column lookups on customer_id
-- Drop idx_a unless there is a covering-index reason to keep it

-- BAD: Index on expression but querying raw column
CREATE INDEX idx_lower_email ON users(LOWER(email));
SELECT * FROM users WHERE email = 'Jane@Example.com';  -- won't use index
-- Must match: WHERE LOWER(email) = 'jane@example.com'

-- BAD: Too-wide covering index
CREATE INDEX idx_everything ON orders(customer_id, order_date, status, total_amount, notes, created_at, updated_at);
-- Wide indexes consume excessive storage and slow writes
-- Only include columns that are genuinely needed for index-only scans
```

## Cross-Database Index Features

| Feature | PostgreSQL | MySQL (InnoDB) | SQL Server |
|---------|-----------|----------------|------------|
| B-tree | Default | Default | Default (clustered or non-clustered) |
| Partial index | `WHERE` clause | Not supported | `WHERE` clause (filtered) |
| Covering index | `INCLUDE (cols)` | Add to key columns | `INCLUDE (cols)` |
| GIN | Full support | Not available | Not available |
| GiST | Full support | Not available | Spatial index |
| Expression index | Full support | Generated columns + index | Computed columns + index |
| Concurrent build | `CREATE INDEX CONCURRENTLY` | Online DDL (`ALGORITHM=INPLACE`) | `ONLINE = ON` |
