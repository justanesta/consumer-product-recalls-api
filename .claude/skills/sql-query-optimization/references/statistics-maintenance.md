# Statistics Maintenance

Guide to database statistics, how they drive query optimization, and how to keep them accurate.

## Why Statistics Matter

The query optimizer uses statistics to estimate row counts, selectivity, and data distribution at each step of a query plan. When statistics are stale or inaccurate, the optimizer makes bad decisions:
- Chooses sequential scan instead of index scan (or vice versa)
- Picks the wrong join algorithm (hash join when nested loop would be faster)
- Allocates wrong join order for multi-table queries
- Under-allocates memory for sort and hash operations

## PostgreSQL: ANALYZE

### Manual ANALYZE

```sql
-- Analyze a specific table (most common use)
ANALYZE orders;

-- Analyze specific columns only (faster for wide tables)
ANALYZE orders (customer_id, order_date, status);

-- Analyze all tables in the current database
ANALYZE;

-- Verbose output: shows column-level stats gathered
ANALYZE VERBOSE orders;
-- Output:
-- INFO: analyzing "public.orders"
-- INFO: "orders": scanned 11370 of 11370 pages, 1000000 live rows, 0 dead rows;
--       30000 rows in sample, 1000000 estimated total rows
```

### Checking Statistics Freshness

```sql
-- When were stats last updated?
SELECT
    schemaname,
    relname AS table_name,
    last_analyze,
    last_autoanalyze,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze
FROM pg_stat_user_tables
WHERE relname = 'orders';

-- n_mod_since_analyze: rows modified since last ANALYZE
-- If this is high relative to n_live_tup, statistics are likely stale
```

### Viewing Gathered Statistics

```sql
-- Column-level statistics: most common values and histogram bounds
SELECT
    attname AS column_name,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE tablename = 'orders' AND attname = 'status';

-- n_distinct: estimated number of distinct values
--   Positive: absolute count (e.g., 5 means 5 distinct values)
--   Negative: fraction of total rows (e.g., -0.5 means 50% are distinct)
-- most_common_vals: the most frequently occurring values
-- most_common_freqs: frequency of each MCV (sums to < 1.0)
-- histogram_bounds: equal-frequency histogram for non-MCV values
```

### Increasing Statistics Target

For columns with complex distributions, increase the number of histogram buckets.

```sql
-- Default statistics target is 100 (100 histogram buckets)
-- Increase for columns where the optimizer consistently misestimates
ALTER TABLE orders ALTER COLUMN order_date SET STATISTICS 500;
ALTER TABLE orders ALTER COLUMN customer_id SET STATISTICS 1000;

-- Then re-analyze to gather more detailed stats
ANALYZE orders;

-- Global default (affects all columns in new ANALYZE runs)
SET default_statistics_target = 200;

-- Check current setting for a column
SELECT attname, attstattarget
FROM pg_attribute
WHERE attrelid = 'orders'::regclass AND attstattarget > 0;
```

### Extended Statistics (PostgreSQL 10+)

Standard per-column statistics miss correlations between columns. Extended statistics capture multi-column dependencies.

```sql
-- The optimizer underestimates because it assumes city and state are independent
-- In reality, city = 'San Francisco' implies state = 'CA'
SELECT * FROM addresses
WHERE city = 'San Francisco' AND state = 'CA';

-- Create extended statistics for correlated columns
CREATE STATISTICS stat_city_state (dependencies)
ON city, state FROM addresses;
ANALYZE addresses;

-- PostgreSQL 12+: n-distinct extended statistics
CREATE STATISTICS stat_city_state_ndistinct (ndistinct)
ON city, state FROM addresses;

-- PostgreSQL 14+: MCV (most common value) lists for column combinations
CREATE STATISTICS stat_city_state_mcv (mcv)
ON city, state FROM addresses;
```

## PostgreSQL: Auto-Vacuum and Auto-Analyze

Auto-analyze runs automatically when enough rows have been modified.

```sql
-- Default trigger: analyze when 10% of rows + 50 rows have changed
-- Formula: autovacuum_analyze_threshold + autovacuum_analyze_scale_factor * n_live_tup
-- Default: 50 + 0.1 * n_live_tup

-- For a table with 10M rows, auto-analyze triggers after 1,000,050 modifications
-- This may be too infrequent; lower the scale factor for critical tables

-- Per-table auto-analyze tuning
ALTER TABLE orders SET (
    autovacuum_analyze_scale_factor = 0.02,    -- 2% instead of 10%
    autovacuum_analyze_threshold = 1000
);
-- Now triggers after 1000 + 0.02 * 10M = 201,000 modifications

-- Check auto-vacuum settings
SELECT name, setting, short_desc
FROM pg_settings
WHERE name LIKE 'autovacuum%';
```

### Auto-Vacuum Tuning for Large Tables

```sql
-- Large tables need more aggressive vacuum/analyze settings
ALTER TABLE events SET (
    autovacuum_vacuum_scale_factor = 0.01,     -- vacuum after 1% dead rows
    autovacuum_analyze_scale_factor = 0.02,    -- analyze after 2% modifications
    autovacuum_vacuum_cost_delay = 10,         -- less delay between vacuum cycles
    autovacuum_vacuum_cost_limit = 1000        -- higher I/O budget for vacuum
);

-- Monitor auto-vacuum progress
SELECT
    relname,
    last_autovacuum,
    last_autoanalyze,
    autovacuum_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE relname IN ('orders', 'events', 'line_items')
ORDER BY n_live_tup DESC;
```

## SQL Server: UPDATE STATISTICS

```sql
-- Update statistics for a specific table
UPDATE STATISTICS dbo.orders;

-- Update statistics for a specific index
UPDATE STATISTICS dbo.orders idx_orders_customer_id;

-- Full scan (most accurate, most expensive)
UPDATE STATISTICS dbo.orders WITH FULLSCAN;

-- Sample-based (faster, slightly less accurate)
UPDATE STATISTICS dbo.orders WITH SAMPLE 30 PERCENT;

-- Update all statistics in the database
EXEC sp_updatestats;
```

### SQL Server: Viewing Statistics

```sql
-- View statistics details
DBCC SHOW_STATISTICS ('dbo.orders', 'idx_orders_customer_id');
-- Shows: header (rows, rows sampled, steps), density vector, histogram

-- View all statistics objects on a table
SELECT
    s.name AS stats_name,
    s.auto_created,
    s.user_created,
    sp.last_updated,
    sp.rows,
    sp.rows_sampled,
    sp.modification_counter
FROM sys.stats s
CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
WHERE s.object_id = OBJECT_ID('dbo.orders');

-- modification_counter: rows changed since last stats update
-- Large values indicate stale statistics
```

### SQL Server: Auto-Update Statistics

```sql
-- Check if auto-update is enabled
SELECT
    name,
    is_auto_update_stats_on,
    is_auto_update_stats_async_on
FROM sys.databases
WHERE name = DB_NAME();

-- Auto-update triggers when ~20% of rows change (simplified)
-- For large tables, this threshold is too high
-- SQL Server 2016+ with trace flag 2371: dynamic threshold that decreases as table grows

-- Enable trace flag 2371 for dynamic auto-update thresholds
DBCC TRACEON(2371, -1);

-- Async stats update (recommended for OLTP): query uses old stats, update happens in background
ALTER DATABASE MyDB SET AUTO_UPDATE_STATISTICS_ASYNC ON;
```

## MySQL: ANALYZE TABLE

```sql
-- Analyze table to update index statistics
ANALYZE TABLE orders;

-- MySQL InnoDB statistics are based on random index page samples
-- Default sample: 20 pages per index (often insufficient for large tables)

-- Increase the sample size for better accuracy
SET GLOBAL innodb_stats_persistent_sample_pages = 100;

-- Per-table sampling configuration
ALTER TABLE orders STATS_SAMPLE_PAGES = 200;
ANALYZE TABLE orders;
```

### MySQL: Checking Statistics

```sql
-- View index cardinality estimates
SHOW INDEX FROM orders;
-- Cardinality column shows estimated distinct values per index

-- InnoDB persistent statistics (stored in mysql.innodb_table_stats)
SELECT * FROM mysql.innodb_table_stats WHERE table_name = 'orders';
SELECT * FROM mysql.innodb_index_stats WHERE table_name = 'orders';
```

## Detecting Stale Statistics

### The Symptom: Estimated vs Actual Row Mismatch

```sql
-- PostgreSQL: large discrepancy between estimated and actual rows
EXPLAIN ANALYZE
SELECT * FROM orders WHERE status = 'pending';

-- Stale stats:
-- Seq Scan on orders (cost=... rows=500000 ...) (actual ... rows=2340 ...)
-- Estimated 500K rows but only 2340 actual -> stats think 'pending' is common
-- Fix: ANALYZE orders;
```

### Automated Monitoring

```sql
-- PostgreSQL: query to find tables needing ANALYZE
SELECT
    schemaname, relname,
    n_live_tup,
    n_mod_since_analyze,
    ROUND(100.0 * n_mod_since_analyze / NULLIF(n_live_tup, 0), 1) AS pct_modified,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE n_mod_since_analyze > 10000
ORDER BY n_mod_since_analyze DESC;
```

```sql
-- SQL Server: find statistics that need updating
SELECT
    OBJECT_NAME(s.object_id) AS table_name,
    s.name AS stats_name,
    sp.last_updated,
    sp.rows,
    sp.modification_counter,
    ROUND(100.0 * sp.modification_counter / NULLIF(sp.rows, 0), 1) AS pct_modified
FROM sys.stats s
CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
WHERE sp.modification_counter > 10000
ORDER BY sp.modification_counter DESC;
```

## When to Manually Run Statistics Updates

Run ANALYZE or UPDATE STATISTICS after:
1. **Bulk data loads** -- INSERT of > 10% of the table's rows
2. **Large DELETE operations** -- Removing significant portions of data
3. **Schema changes** -- Adding columns, changing types
4. **After creating new indexes** -- Index statistics may not exist yet
5. **Before critical reporting queries** -- Ensure optimal plans for important workloads
6. **After partition maintenance** -- Adding or detaching partitions

```sql
-- PostgreSQL: post-ETL statistics refresh pattern
BEGIN;
-- Bulk load
COPY orders FROM '/data/orders_2025.csv' WITH (FORMAT csv, HEADER);
COMMIT;

-- Immediately refresh statistics
ANALYZE orders;
-- Optionally vacuum to reclaim dead tuple space
VACUUM ANALYZE orders;
```

## Histogram Deep Dive

Histograms divide column values into buckets of approximately equal frequency. They help the optimizer estimate selectivity for range predicates.

```sql
-- PostgreSQL: view histogram buckets for order_date
SELECT
    attname,
    array_length(histogram_bounds, 1) AS num_buckets,
    histogram_bounds
FROM pg_stats
WHERE tablename = 'orders' AND attname = 'order_date';

-- If the histogram has 100 buckets for 1M rows, each bucket represents ~10K rows
-- The optimizer uses linear interpolation within buckets for range estimates

-- Increase granularity for better estimates on skewed data
ALTER TABLE orders ALTER COLUMN order_date SET STATISTICS 500;
ANALYZE orders;
-- Now 500 buckets -> each represents ~2K rows -> more accurate range estimates
```

## Maintenance Schedule Recommendations

| Scenario | Frequency | Method |
|----------|-----------|--------|
| OLTP tables (steady writes) | Auto-analyze (default) | Tune scale factor to 2-5% |
| Data warehouse (batch loads) | After each ETL run | Manual ANALYZE / UPDATE STATISTICS |
| Partitioned tables | After adding/dropping partitions | ANALYZE on affected partitions |
| Post-migration | Immediately | Full ANALYZE on all tables |
| Reporting tables | Before peak hours | Scheduled ANALYZE job |
