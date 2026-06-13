# Sargable Queries

A predicate is **sargable** (Search ARGument ABLE) when the database engine can use an index seek to evaluate it. Non-sargable predicates force full table or index scans because the optimizer cannot navigate the B-tree efficiently.

## The Core Rule

**Never apply a function, operator, or transformation to an indexed column in a WHERE clause.** The index stores the raw column values; wrapping the column changes the lookup value at every row, preventing a seek.

## Sargable vs Non-Sargable Patterns

### Date Functions

```sql
-- NON-SARGABLE: YEAR() wraps the indexed column
SELECT * FROM orders
WHERE YEAR(order_date) = 2025;
-- Optimizer cannot seek the index; it evaluates YEAR() on every row

-- SARGABLE: direct range comparison on the raw column
SELECT * FROM orders
WHERE order_date >= '2025-01-01'
  AND order_date < '2026-01-01';
-- Index seek on order_date range; reads only matching leaf pages
```

```sql
-- NON-SARGABLE: EXTRACT wraps the column
SELECT * FROM events
WHERE EXTRACT(MONTH FROM event_date) = 6
  AND EXTRACT(YEAR FROM event_date) = 2025;

-- SARGABLE: rewrite as a range
SELECT * FROM events
WHERE event_date >= '2025-06-01'
  AND event_date < '2025-07-01';
```

```sql
-- NON-SARGABLE: DATEADD on the column side (SQL Server)
SELECT * FROM subscriptions
WHERE DATEADD(day, 30, start_date) >= GETDATE();

-- SARGABLE: move the arithmetic to the constant side
SELECT * FROM subscriptions
WHERE start_date >= DATEADD(day, -30, GETDATE());
```

### String Functions

```sql
-- NON-SARGABLE: UPPER() wraps the indexed column
SELECT * FROM users WHERE UPPER(email) = 'JOHN@EXAMPLE.COM';

-- SARGABLE OPTION 1: expression index (PostgreSQL)
CREATE INDEX idx_users_lower_email ON users (LOWER(email));
SELECT * FROM users WHERE LOWER(email) = 'john@example.com';

-- SARGABLE OPTION 2: citext type (PostgreSQL)
ALTER TABLE users ALTER COLUMN email TYPE citext;
SELECT * FROM users WHERE email = 'John@Example.com';

-- SARGABLE OPTION 3: case-insensitive collation (SQL Server)
-- Column already uses CI collation by default
SELECT * FROM users WHERE email = 'John@Example.com';
```

```sql
-- NON-SARGABLE: SUBSTRING wraps the column
SELECT * FROM products WHERE SUBSTRING(sku, 1, 3) = 'ELC';

-- SARGABLE: use LIKE with a prefix pattern
SELECT * FROM products WHERE sku LIKE 'ELC%';
-- Prefix LIKE uses an index range scan on the B-tree
```

```sql
-- NON-SARGABLE: CONCAT on the indexed column
SELECT * FROM employees
WHERE CONCAT(first_name, ' ', last_name) = 'John Smith';

-- SARGABLE: filter on individual indexed columns
SELECT * FROM employees
WHERE first_name = 'John' AND last_name = 'Smith';
```

### LIKE Patterns

```sql
-- SARGABLE: prefix pattern (index can seek to 'Smi' in the B-tree)
SELECT * FROM customers WHERE last_name LIKE 'Smi%';

-- NON-SARGABLE: leading wildcard (must scan every value)
SELECT * FROM customers WHERE last_name LIKE '%mith';

-- NON-SARGABLE: leading wildcard with prefix
SELECT * FROM customers WHERE email LIKE '%@gmail.com';

-- SARGABLE ALTERNATIVE for suffix/contains: use a reversed column + index
ALTER TABLE customers ADD COLUMN email_reversed TEXT
    GENERATED ALWAYS AS (REVERSE(email)) STORED;
CREATE INDEX idx_email_reversed ON customers (email_reversed);
SELECT * FROM customers WHERE email_reversed LIKE REVERSE('%@gmail.com');
-- Becomes: WHERE email_reversed LIKE 'moc.liamg@%'  (prefix match!)

-- For full-text search needs, use GIN/GiST indexes or dedicated search engines
```

### Arithmetic on Columns

```sql
-- NON-SARGABLE: arithmetic on the indexed column
SELECT * FROM products WHERE price * 1.1 > 100;
-- Optimizer evaluates price * 1.1 for every row

-- SARGABLE: move arithmetic to the constant side
SELECT * FROM products WHERE price > 100 / 1.1;
-- Optimizer seeks the index to price > 90.909...

-- NON-SARGABLE: addition on the indexed column
SELECT * FROM accounts WHERE balance + pending_credit > 10000;

-- SARGABLE (if only balance is indexed):
SELECT * FROM accounts WHERE balance > 10000 - pending_credit;
-- Note: this only works if pending_credit is a constant or another table's value.
-- If both columns are in the same row, you may need an expression index:
CREATE INDEX idx_total_balance ON accounts ((balance + pending_credit));
```

## Implicit Type Casting

Implicit type conversions applied to the indexed column prevent index usage.

```sql
-- NON-SARGABLE: comparing VARCHAR column to INTEGER
-- The engine implicitly casts the column: CAST(phone_number AS INTEGER)
SELECT * FROM contacts WHERE phone_number = 5551234;
-- phone_number is VARCHAR; the implicit cast wraps the column

-- SARGABLE: use the correct type for the literal
SELECT * FROM contacts WHERE phone_number = '5551234';
```

```sql
-- NON-SARGABLE: comparing DATE column to TIMESTAMP string
-- PostgreSQL may implicitly cast the column to timestamp
SELECT * FROM orders WHERE order_date = '2025-06-15 00:00:00';
-- If order_date is DATE, the implicit cast to TIMESTAMP wraps the column

-- SARGABLE: match the literal type to the column type
SELECT * FROM orders WHERE order_date = '2025-06-15';
-- Or explicitly cast the literal, never the column:
SELECT * FROM orders WHERE order_date = '2025-06-15'::DATE;
```

```sql
-- MySQL-specific trap: comparing UTF8 column with latin1 literal
-- Charset mismatch forces conversion on the column side
-- Fix: ensure connection charset matches column charset
SET NAMES utf8mb4;
```

## Negation Predicates

```sql
-- NON-SARGABLE (usually): != or <> requires scanning all non-matching values
SELECT * FROM orders WHERE status <> 'cancelled';
-- If 95% of orders are not cancelled, the optimizer may still seq scan

-- SARGABLE ALTERNATIVE: if the positive set is small, use IN
SELECT * FROM orders WHERE status IN ('pending', 'shipped', 'delivered');

-- For low-cardinality columns, a partial index is often better:
CREATE INDEX idx_orders_pending ON orders (order_date)
WHERE status = 'pending';
```

```sql
-- NON-SARGABLE: NOT IN or NOT LIKE
SELECT * FROM products WHERE category NOT IN ('archived', 'deleted');

-- SARGABLE with partial index:
CREATE INDEX idx_products_active ON products (category, name)
WHERE category NOT IN ('archived', 'deleted');
-- The partial index predicate matches the query filter exactly
```

## OR Predicates

```sql
-- POTENTIALLY NON-SARGABLE: OR across different columns
SELECT * FROM orders
WHERE customer_id = 42 OR shipping_city = 'New York';
-- Optimizer may not use either index (depends on engine version)

-- SARGABLE: rewrite as UNION of two indexed queries
SELECT * FROM orders WHERE customer_id = 42
UNION
SELECT * FROM orders WHERE shipping_city = 'New York';
-- Each branch uses its own index

-- SARGABLE (PostgreSQL): BitmapOr can combine two index scans
-- PostgreSQL optimizer often handles OR well with bitmap scans:
-- BitmapOr
--   -> Bitmap Index Scan on idx_customer_id
--   -> Bitmap Index Scan on idx_shipping_city
```

## IS NULL and IS NOT NULL

```sql
-- B-tree indexes DO include NULLs (in PostgreSQL and SQL Server)
-- So IS NULL is sargable:
SELECT * FROM orders WHERE cancelled_at IS NULL;
-- Uses index if one exists on cancelled_at

-- However, in MySQL InnoDB, IS NULL is sargable but IS NOT NULL
-- may not use the index if most rows are NOT NULL

-- Partial index for NULL checks (PostgreSQL):
CREATE INDEX idx_orders_not_cancelled ON orders (order_id)
WHERE cancelled_at IS NULL;
```

## Testing Sargability

Always verify with EXPLAIN:

```sql
-- Step 1: run EXPLAIN on the original query
EXPLAIN ANALYZE
SELECT * FROM orders WHERE YEAR(order_date) = 2025;
-- Look for: Seq Scan with "Rows Removed by Filter"

-- Step 2: rewrite and re-run EXPLAIN
EXPLAIN ANALYZE
SELECT * FROM orders
WHERE order_date >= '2025-01-01' AND order_date < '2026-01-01';
-- Look for: Index Scan or Index Only Scan

-- Step 3: compare actual execution times
```

## Quick Reference: Common Rewrites

| Non-Sargable | Sargable Rewrite |
|-------------|-----------------|
| `WHERE YEAR(col) = 2025` | `WHERE col >= '2025-01-01' AND col < '2026-01-01'` |
| `WHERE UPPER(col) = 'X'` | Expression index on `UPPER(col)` or use citext |
| `WHERE col + 1 = 10` | `WHERE col = 9` |
| `WHERE col * tax > 100` | `WHERE col > 100 / tax` |
| `WHERE SUBSTRING(col,1,3) = 'ABC'` | `WHERE col LIKE 'ABC%'` |
| `WHERE col LIKE '%xyz'` | Reverse column + `LIKE 'zyx%'` or full-text search |
| `WHERE CAST(col AS INT) = 5` | `WHERE col = '5'` (match the column type) |
| `WHERE COALESCE(col, 0) > 10` | `WHERE col > 10` (if NULL rows are irrelevant) |
| `WHERE col IS NOT NULL AND col <> 'x'` | Partial index `WHERE col <> 'x'` |
