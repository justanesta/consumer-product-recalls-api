# Dynamic SQL Patterns

## Why Dynamic SQL

```
Use dynamic SQL when query structure must change at runtime: dynamic table/column
names, optional filters, pivot columns from data, or admin scripts across tables.
Always prefer static SQL when only parameter values change.
```

## PostgreSQL: EXECUTE with USING (Parameterized)

```sql
-- Safe: parameters passed via USING are not subject to SQL injection
CREATE OR REPLACE FUNCTION search_orders(
    p_customer_id INTEGER DEFAULT NULL,
    p_status      TEXT DEFAULT NULL,
    p_min_amount  NUMERIC DEFAULT NULL,
    p_start_date  DATE DEFAULT NULL,
    p_end_date    DATE DEFAULT NULL
) RETURNS SETOF orders
LANGUAGE plpgsql AS $$
DECLARE
    v_sql TEXT;
BEGIN
    v_sql := 'SELECT * FROM orders WHERE 1=1';

    IF p_customer_id IS NOT NULL THEN
        v_sql := v_sql || ' AND customer_id = $1';
    END IF;
    IF p_status IS NOT NULL THEN
        v_sql := v_sql || ' AND status = $2';
    END IF;
    IF p_min_amount IS NOT NULL THEN
        v_sql := v_sql || ' AND total_amount >= $3';
    END IF;
    IF p_start_date IS NOT NULL THEN
        v_sql := v_sql || ' AND order_date >= $4';
    END IF;
    IF p_end_date IS NOT NULL THEN
        v_sql := v_sql || ' AND order_date <= $5';
    END IF;

    v_sql := v_sql || ' ORDER BY order_date DESC';

    RETURN QUERY EXECUTE v_sql
        USING p_customer_id, p_status, p_min_amount, p_start_date, p_end_date;
END;
$$;

-- Call with any combination of filters
SELECT * FROM search_orders(p_status => 'shipped', p_min_amount => 100);
SELECT * FROM search_orders(p_customer_id => 42, p_start_date => '2025-01-01');
```

## SQL Injection Prevention

```sql
-- DANGEROUS: string concatenation with user input
-- NEVER DO THIS
CREATE FUNCTION bad_search(p_table TEXT, p_name TEXT)
RETURNS SETOF RECORD LANGUAGE plpgsql AS $$
BEGIN
    -- Attacker sends p_name = "'; DROP TABLE customers; --"
    RETURN QUERY EXECUTE
        'SELECT * FROM ' || p_table || ' WHERE name = ''' || p_name || '''';
END;
$$;

-- SAFE: use format() with %I for identifiers and %L for literals
CREATE FUNCTION safe_search(p_table TEXT, p_name TEXT)
RETURNS SETOF RECORD LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT * FROM %I WHERE name = %L',
        p_table,  -- %I: safely quoted identifier (table/column name)
        p_name    -- %L: safely quoted literal value
    );
END;
$$;

-- SAFEST: use USING for values whenever possible
CREATE FUNCTION safest_search(p_name TEXT)
RETURNS SETOF customers LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY EXECUTE 'SELECT * FROM customers WHERE name = $1'
        USING p_name;
END;
$$;

-- format() specifiers:
-- %I = identifier (table, column, schema names) — double-quoted if needed
-- %L = literal value — properly escaped and single-quoted
-- %s = simple string substitution (no escaping — avoid for user input)
```

## SQL Server: sp_executesql (Parameterized)

```sql
-- sp_executesql is always preferred over EXEC() for parameterized queries
DECLARE @sql NVARCHAR(MAX);
DECLARE @params NVARCHAR(MAX);

SET @sql = N'
    SELECT order_id, customer_id, total_amount, order_date
    FROM orders
    WHERE 1=1';

SET @params = N'@p_customer_id INT, @p_status VARCHAR(50), @p_min_amount DECIMAL(12,2)';

IF @customer_id IS NOT NULL
    SET @sql = @sql + N' AND customer_id = @p_customer_id';
IF @status IS NOT NULL
    SET @sql = @sql + N' AND status = @p_status';
IF @min_amount IS NOT NULL
    SET @sql = @sql + N' AND total_amount >= @p_min_amount';

SET @sql = @sql + N' ORDER BY order_date DESC';

EXEC sp_executesql @sql, @params,
    @p_customer_id = @customer_id,
    @p_status = @status,
    @p_min_amount = @min_amount;

-- For dynamic table names (cannot be parameterized), use QUOTENAME
DECLARE @table_name SYSNAME = 'orders';
SET @sql = N'SELECT * FROM ' + QUOTENAME(@table_name) + N' WHERE status = @p_status';
EXEC sp_executesql @sql, N'@p_status VARCHAR(50)', @p_status = 'active';
```

## MySQL: PREPARE and EXECUTE

```sql
-- MySQL parameterized dynamic SQL
SET @sql = 'SELECT * FROM orders WHERE customer_id = ? AND status = ?';
SET @cid = 42;
SET @status = 'shipped';

PREPARE stmt FROM @sql;
EXECUTE stmt USING @cid, @status;
DEALLOCATE PREPARE stmt;

-- Dynamic table names in MySQL (no QUOTENAME equivalent)
-- Must validate table name manually
DELIMITER //
CREATE PROCEDURE sp_count_rows(IN p_table_name VARCHAR(64))
BEGIN
    -- Validate the table exists to prevent injection
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = p_table_name
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid table name';
    END IF;

    SET @sql = CONCAT('SELECT COUNT(*) AS row_count FROM `', p_table_name, '`');
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
END //
DELIMITER ;
```

## Dynamic Pivot Queries

```sql
-- PostgreSQL: generate a pivot query dynamically from data
CREATE OR REPLACE FUNCTION dynamic_pivot_sales_by_region()
RETURNS TEXT
LANGUAGE plpgsql AS $$
DECLARE
    v_columns TEXT;
    v_sql TEXT;
BEGIN
    -- Build the column list from actual data
    SELECT string_agg(
        format('SUM(CASE WHEN region = %L THEN total_amount ELSE 0 END) AS %I',
               region, region),
        ', ' ORDER BY region
    ) INTO v_columns
    FROM (SELECT DISTINCT region FROM orders) r;

    v_sql := format(
        'SELECT DATE_TRUNC(''month'', order_date) AS month, %s FROM orders GROUP BY 1 ORDER BY 1',
        v_columns
    );

    RETURN v_sql;
END;
$$;

-- Execute it
DO $$
DECLARE
    v_sql TEXT;
BEGIN
    v_sql := dynamic_pivot_sales_by_region();
    RAISE NOTICE '%', v_sql;
    -- Or: EXECUTE v_sql;
END $$;

-- SQL Server: dynamic pivot
DECLARE @columns NVARCHAR(MAX), @sql NVARCHAR(MAX);

SELECT @columns = STRING_AGG(QUOTENAME(region), ', ')
FROM (SELECT DISTINCT region FROM orders) AS r;

SET @sql = N'
SELECT order_month, ' + @columns + N'
FROM (
    SELECT
        FORMAT(order_date, ''yyyy-MM'') AS order_month,
        region,
        total_amount
    FROM orders
) src
PIVOT (
    SUM(total_amount)
    FOR region IN (' + @columns + N')
) pvt
ORDER BY order_month';

EXEC sp_executesql @sql;
```

## Dynamic Table and Schema Operations

```sql
-- PostgreSQL: administrative script to add a column to all tables with a pattern
CREATE OR REPLACE PROCEDURE add_audit_columns(p_schema TEXT DEFAULT 'public')
LANGUAGE plpgsql AS $$
DECLARE
    v_table RECORD;
BEGIN
    FOR v_table IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = p_schema
          AND table_type = 'BASE TABLE'
          AND table_name NOT LIKE 'pg_%'
    LOOP
        -- Check if column already exists
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = p_schema
              AND table_name = v_table.table_name
              AND column_name = 'updated_at'
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I.%I ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW()',
                p_schema, v_table.table_name
            );
            RAISE NOTICE 'Added updated_at to %.%', p_schema, v_table.table_name;
        END IF;
    END LOOP;
END;
$$;
```

## Debugging Dynamic SQL

```sql
-- Always RAISE NOTICE the generated SQL during development
CREATE OR REPLACE FUNCTION debug_dynamic_query(p_filters JSONB)
RETURNS SETOF orders
LANGUAGE plpgsql AS $$
DECLARE v_sql TEXT := 'SELECT * FROM orders WHERE 1=1'; v_key TEXT; v_value TEXT;
BEGIN
    FOR v_key, v_value IN SELECT * FROM jsonb_each_text(p_filters) LOOP
        v_sql := v_sql || format(' AND %I = %L', v_key, v_value);
    END LOOP;
    RAISE NOTICE 'Executing: %', v_sql;
    RETURN QUERY EXECUTE v_sql;
END;
$$;

-- SELECT * FROM debug_dynamic_query('{"status": "shipped", "region": "West"}');
-- NOTICE: Executing: SELECT * FROM orders WHERE 1=1 AND status = 'shipped' AND region = 'West'
```

## Dynamic SQL Security Checklist

```
1. NEVER concatenate user input directly into SQL strings
2. Use USING / sp_executesql / PREPARE for value parameters
3. Use format(%I) / QUOTENAME() for identifiers (table/column names)
4. Validate dynamic table names against information_schema
5. Limit which tables/columns can be specified dynamically
6. Use application-level allowlists for dynamic identifiers
7. Log all generated SQL for audit and debugging
8. Test with SQL injection payloads: ' OR 1=1 --, '; DROP TABLE x; --
9. Grant EXECUTE on the function/procedure, not on underlying tables
10. Consider using views or static queries if the dynamic need is limited
```
