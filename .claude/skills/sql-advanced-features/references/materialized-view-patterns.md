# Materialized View Patterns

## Basic Materialized Views (PostgreSQL)

```sql
-- Create a materialized view for a dashboard summary
CREATE MATERIALIZED VIEW mv_sales_dashboard AS
SELECT
    DATE_TRUNC('day', o.order_date) AS sale_date,
    p.category,
    r.region_name,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS total_revenue,
    AVG(o.total_amount) AS avg_order_value,
    COUNT(DISTINCT o.customer_id) AS unique_customers
FROM orders o
INNER JOIN products p ON o.product_id = p.product_id
INNER JOIN regions r ON o.region_id = r.region_id
WHERE o.order_status = 'completed'
GROUP BY DATE_TRUNC('day', o.order_date), p.category, r.region_name
WITH DATA;

-- Create indexes on the materialized view for query performance
CREATE INDEX idx_mv_sales_date ON mv_sales_dashboard (sale_date);
CREATE INDEX idx_mv_sales_category ON mv_sales_dashboard (category);
CREATE UNIQUE INDEX idx_mv_sales_unique
    ON mv_sales_dashboard (sale_date, category, region_name);
```

## Creating Without Data

```sql
-- Create the structure but defer populating until needed
CREATE MATERIALIZED VIEW mv_quarterly_report AS
SELECT
    DATE_TRUNC('quarter', order_date) AS quarter,
    product_category,
    SUM(revenue) AS total_revenue,
    COUNT(DISTINCT customer_id) AS customer_count
FROM order_summary
GROUP BY DATE_TRUNC('quarter', order_date), product_category
WITH NO DATA;

-- Querying before populating raises an error:
-- ERROR: materialized view "mv_quarterly_report" has not been populated

-- Populate when ready
REFRESH MATERIALIZED VIEW mv_quarterly_report;
```

## Full Refresh Strategy

```sql
-- Standard full refresh (blocks reads during refresh)
REFRESH MATERIALIZED VIEW mv_sales_dashboard;

-- Wrap in a function for scheduling
CREATE OR REPLACE FUNCTION refresh_sales_dashboard()
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'Starting refresh of mv_sales_dashboard at %', NOW();
    REFRESH MATERIALIZED VIEW mv_sales_dashboard;
    RAISE NOTICE 'Completed refresh at %', NOW();

    -- Log the refresh
    INSERT INTO mv_refresh_log (view_name, refreshed_at, row_count)
    SELECT 'mv_sales_dashboard', NOW(), COUNT(*) FROM mv_sales_dashboard;
END;
$$;
```

## Concurrent Refresh (Non-Blocking)

```sql
-- CONCURRENTLY allows reads during refresh (requires a UNIQUE index)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_dashboard;

-- How it works:
-- 1. Builds new data in a temporary space
-- 2. Compares new data with existing using the unique index
-- 3. Applies only the differences (inserts, updates, deletes)
-- 4. Readers see the old data until the swap completes

-- Trade-offs:
-- + No read blocking during refresh
-- - Slower than full refresh (must diff)
-- - Requires a UNIQUE index on the materialized view
-- - Uses more temporary disk space
```

## Auto-Refresh with pg_cron

```sql
-- Install pg_cron extension (PostgreSQL)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Refresh every hour
SELECT cron.schedule(
    'refresh-sales-dashboard',
    '0 * * * *',  -- cron expression: every hour on the hour
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_dashboard'
);

-- Refresh daily at 2 AM
SELECT cron.schedule(
    'refresh-quarterly-report',
    '0 2 * * *',
    'SELECT refresh_sales_dashboard()'
);

-- List scheduled jobs
SELECT * FROM cron.job;

-- Remove a scheduled refresh
SELECT cron.unschedule('refresh-sales-dashboard');
```

## Incremental Refresh Pattern (Manual)

```sql
-- PostgreSQL doesn't natively support incremental refresh.
-- Simulate it with a table + merge approach.

-- Step 1: Track the high-water mark
CREATE TABLE mv_refresh_state (
    view_name TEXT PRIMARY KEY,
    last_refreshed_at TIMESTAMP NOT NULL DEFAULT '1970-01-01'
);

INSERT INTO mv_refresh_state VALUES ('order_daily_summary', '1970-01-01');

-- Step 2: Incremental refresh procedure
CREATE OR REPLACE PROCEDURE incremental_refresh_daily_summary()
LANGUAGE plpgsql AS $$
DECLARE
    v_last_refresh TIMESTAMP;
BEGIN
    SELECT last_refreshed_at INTO v_last_refresh
    FROM mv_refresh_state WHERE view_name = 'order_daily_summary';

    -- Delete affected date partitions and re-insert
    DELETE FROM order_daily_summary
    WHERE sale_date >= DATE_TRUNC('day', v_last_refresh);

    INSERT INTO order_daily_summary (sale_date, category, order_count, total_revenue)
    SELECT
        DATE_TRUNC('day', order_date),
        product_category,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    WHERE order_date >= DATE_TRUNC('day', v_last_refresh)
    GROUP BY DATE_TRUNC('day', order_date), product_category;

    -- Update the high-water mark
    UPDATE mv_refresh_state
    SET last_refreshed_at = NOW()
    WHERE view_name = 'order_daily_summary';

    COMMIT;
END;
$$;
```

## SQL Server Indexed Views (Auto-Refresh)

```sql
-- SQL Server indexed views are automatically maintained by the engine
CREATE VIEW dbo.v_product_order_summary
WITH SCHEMABINDING
AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    COUNT_BIG(*) AS order_count,
    SUM(oi.quantity) AS total_quantity,
    SUM(oi.line_total) AS total_revenue
FROM dbo.order_items oi
INNER JOIN dbo.products p ON oi.product_id = p.product_id
GROUP BY p.product_id, p.product_name, p.category;
GO

-- Materialize with a unique clustered index
CREATE UNIQUE CLUSTERED INDEX IX_product_order_summary
    ON dbo.v_product_order_summary (product_id);
GO

-- Restrictions for indexed views in SQL Server:
-- - Must use SCHEMABINDING
-- - Must use COUNT_BIG(*) instead of COUNT(*)
-- - No OUTER joins, subqueries, UNION, DISTINCT, TOP, ORDER BY
-- - No non-deterministic functions (GETDATE, NEWID, etc.)
-- - Enterprise Edition uses indexed views automatically;
--   Standard Edition requires WITH (NOEXPAND) hint
SELECT * FROM dbo.v_product_order_summary WITH (NOEXPAND)
WHERE category = 'Electronics';
```

## MySQL Simulated Materialized Views

```sql
-- MySQL has no native materialized views — simulate with table + event.
CREATE TABLE mv_customer_stats (
    customer_id INT PRIMARY KEY, total_orders INT DEFAULT 0,
    total_spent DECIMAL(12,2) DEFAULT 0.00, last_order_date DATE,
    refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

DELIMITER //
CREATE PROCEDURE sp_refresh_customer_stats()
BEGIN
    TRUNCATE TABLE mv_customer_stats;
    INSERT INTO mv_customer_stats (customer_id, total_orders, total_spent, last_order_date, refreshed_at)
    SELECT c.customer_id, COUNT(o.order_id), COALESCE(SUM(o.total_amount), 0), MAX(o.order_date), NOW()
    FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id;
END //
DELIMITER ;

-- Schedule with MySQL Event Scheduler
SET GLOBAL event_scheduler = ON;
CREATE EVENT ev_refresh_customer_stats ON SCHEDULE EVERY 1 HOUR
DO CALL sp_refresh_customer_stats();
```

## Refresh Monitoring and Alerting

```sql
-- Track refresh history for monitoring
CREATE TABLE mv_refresh_log (
    log_id SERIAL PRIMARY KEY,
    view_name TEXT NOT NULL,
    refresh_type TEXT NOT NULL DEFAULT 'full',
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    row_count BIGINT,
    status TEXT NOT NULL DEFAULT 'running'
);

-- Refresh wrapper with logging and error capture
CREATE OR REPLACE PROCEDURE logged_refresh(p_view_name TEXT, p_concurrent BOOLEAN DEFAULT TRUE)
LANGUAGE plpgsql AS $$
DECLARE v_log_id INTEGER;
BEGIN
    INSERT INTO mv_refresh_log (view_name, refresh_type, started_at, status)
    VALUES (p_view_name, CASE WHEN p_concurrent THEN 'concurrent' ELSE 'full' END, NOW(), 'running')
    RETURNING log_id INTO v_log_id;

    IF p_concurrent THEN
        EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', p_view_name);
    ELSE
        EXECUTE format('REFRESH MATERIALIZED VIEW %I', p_view_name);
    END IF;

    UPDATE mv_refresh_log SET completed_at = NOW(), status = 'success' WHERE log_id = v_log_id;
    COMMIT;
EXCEPTION WHEN OTHERS THEN
    UPDATE mv_refresh_log SET completed_at = NOW(), status = 'failed: ' || SQLERRM WHERE log_id = v_log_id;
    COMMIT; RAISE;
END;
$$;
```

## Staleness Detection

```sql
-- Detect stale materialized views using the refresh log
SELECT view_name, MAX(completed_at) AS last_refresh,
    NOW() - MAX(completed_at) AS time_since_refresh,
    CASE WHEN NOW() - MAX(completed_at) > INTERVAL '2 hours' THEN 'STALE'
         WHEN NOW() - MAX(completed_at) > INTERVAL '1 hour' THEN 'WARNING'
         ELSE 'FRESH' END AS freshness_status
FROM mv_refresh_log WHERE status = 'success'
GROUP BY view_name ORDER BY last_refresh;
```

## Materialized View vs Table vs View Decision Matrix

```
Use a regular VIEW when:
  - Data must always be current (real-time)
  - Underlying query is fast (< 100ms)
  - Query is simple enough for the optimizer to merge

Use a MATERIALIZED VIEW when:
  - Query is expensive (seconds to minutes)
  - Slight staleness is acceptable
  - Data is read far more often than written
  - Dashboard or reporting use case

Use a plain TABLE (manual refresh) when:
  - You need incremental refresh logic
  - Cross-database compatibility is required (MySQL)
  - You need fine-grained control over refresh scheduling
  - You need to partition the materialized data
```
