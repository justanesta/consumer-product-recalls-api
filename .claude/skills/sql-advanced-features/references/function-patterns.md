# Function Patterns

## Scalar Functions

```sql
-- PostgreSQL: scalar function returning a single value
CREATE OR REPLACE FUNCTION calculate_discount(
    p_order_total NUMERIC,
    p_customer_tier TEXT
) RETURNS NUMERIC
LANGUAGE sql IMMUTABLE AS $$
    SELECT ROUND(p_order_total * CASE p_customer_tier
        WHEN 'Platinum' THEN 0.20
        WHEN 'Gold'     THEN 0.15
        WHEN 'Silver'   THEN 0.10
        ELSE 0.00
    END, 2);
$$;

-- Usage in queries
SELECT
    order_id,
    total_amount,
    calculate_discount(total_amount, customer_tier) AS discount,
    total_amount - calculate_discount(total_amount, customer_tier) AS final_price
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id;

-- SQL Server scalar function
CREATE OR ALTER FUNCTION dbo.fn_calculate_discount(
    @order_total DECIMAL(12,2),
    @customer_tier VARCHAR(20)
) RETURNS DECIMAL(12,2)
AS
BEGIN
    RETURN ROUND(@order_total * CASE @customer_tier
        WHEN 'Platinum' THEN 0.20
        WHEN 'Gold'     THEN 0.15
        WHEN 'Silver'   THEN 0.10
        ELSE 0.00
    END, 2);
END;
GO

-- MySQL scalar function
DELIMITER //
CREATE FUNCTION fn_calculate_discount(
    p_order_total DECIMAL(12,2),
    p_customer_tier VARCHAR(20)
) RETURNS DECIMAL(12,2)
DETERMINISTIC
BEGIN
    DECLARE v_rate DECIMAL(4,2);
    SET v_rate = CASE p_customer_tier
        WHEN 'Platinum' THEN 0.20
        WHEN 'Gold'     THEN 0.15
        WHEN 'Silver'   THEN 0.10
        ELSE 0.00
    END;
    RETURN ROUND(p_order_total * v_rate, 2);
END //
DELIMITER ;
```

## Table-Valued Functions (PostgreSQL)

```sql
-- Returns a set of rows — can be used in FROM clause
CREATE OR REPLACE FUNCTION get_top_customers_by_region(
    p_region TEXT,
    p_limit  INTEGER DEFAULT 10
) RETURNS TABLE (
    customer_id    INTEGER,
    customer_name  TEXT,
    total_orders   BIGINT,
    total_revenue  NUMERIC,
    rank           BIGINT
)
LANGUAGE sql STABLE AS $$
    SELECT
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) AS total_orders,
        SUM(o.total_amount) AS total_revenue,
        ROW_NUMBER() OVER (ORDER BY SUM(o.total_amount) DESC) AS rank
    FROM customers c
    INNER JOIN orders o ON c.customer_id = o.customer_id
    WHERE c.region = p_region
    GROUP BY c.customer_id, c.customer_name
    ORDER BY total_revenue DESC
    LIMIT p_limit;
$$;

-- Use like a table in FROM
SELECT * FROM get_top_customers_by_region('West', 5);

-- Join with other tables
SELECT
    t.customer_id,
    t.customer_name,
    t.total_revenue,
    s.subscription_plan
FROM get_top_customers_by_region('West', 20) t
LEFT JOIN subscriptions s ON t.customer_id = s.customer_id;
```

## SQL Server Table-Valued Functions

```sql
-- Inline TVF (preferred — optimizer can inline the plan)
CREATE OR ALTER FUNCTION dbo.fn_top_customers_by_region(
    @region VARCHAR(50), @limit INT
) RETURNS TABLE AS RETURN
    SELECT TOP (@limit) c.customer_id, c.customer_name,
        COUNT(o.order_id) AS total_orders, SUM(o.total_amount) AS total_revenue
    FROM customers c
    INNER JOIN orders o ON c.customer_id = o.customer_id
    WHERE c.region = @region
    GROUP BY c.customer_id, c.customer_name
    ORDER BY SUM(o.total_amount) DESC;
GO

-- Multi-statement TVF (avoid — optimizer cannot inline the plan)
CREATE OR ALTER FUNCTION dbo.fn_customer_order_history(@customer_id INT)
RETURNS @result TABLE (order_id INT, order_date DATE, total_amount DECIMAL(12,2), running_total DECIMAL(12,2))
AS BEGIN
    INSERT INTO @result
    SELECT order_id, order_date, total_amount,
        SUM(total_amount) OVER (ORDER BY order_date)
    FROM orders WHERE customer_id = @customer_id;
    RETURN;
END;
GO

-- CROSS APPLY to call TVF for each row
SELECT c.customer_id, c.customer_name, h.order_date, h.running_total
FROM customers c
CROSS APPLY dbo.fn_customer_order_history(c.customer_id) h
WHERE c.region = 'West';
```

## Volatility Categories (PostgreSQL)

```sql
-- IMMUTABLE: same inputs always produce same output, never reads database
-- The planner can pre-evaluate at planning time
CREATE OR REPLACE FUNCTION celsius_to_fahrenheit(p_celsius NUMERIC)
RETURNS NUMERIC
LANGUAGE sql IMMUTABLE AS $$
    SELECT ROUND(p_celsius * 9.0 / 5.0 + 32, 2);
$$;

-- STABLE: returns same result within a single query scan
-- Can read database but result doesn't change during the statement
CREATE OR REPLACE FUNCTION get_current_tax_rate(p_state TEXT)
RETURNS NUMERIC
LANGUAGE sql STABLE AS $$
    SELECT tax_rate FROM state_tax_rates WHERE state_code = p_state;
$$;

-- VOLATILE (default): can return different results on each call
-- Cannot be optimized away; called for every row
CREATE OR REPLACE FUNCTION generate_tracking_number()
RETURNS TEXT
LANGUAGE plpgsql VOLATILE AS $$
BEGIN
    RETURN 'TRK-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' ||
           LPAD(nextval('tracking_seq')::TEXT, 8, '0');
END;
$$;

-- MySQL equivalents
-- DETERMINISTIC = IMMUTABLE (same inputs, same outputs)
-- NOT DETERMINISTIC = VOLATILE (default)
-- MySQL does not have a STABLE equivalent

-- Impact on indexing:
-- Only IMMUTABLE functions can be used in index expressions
CREATE INDEX idx_temp_f ON weather_readings (celsius_to_fahrenheit(temperature));
```

## Custom Aggregate Functions (PostgreSQL)

```sql
-- Custom aggregate: median using transition and final functions
CREATE AGGREGATE median(NUMERIC) (
    SFUNC = array_append,        -- transition: accumulate values into array
    STYPE = NUMERIC[],
    FINALFUNC = (               -- final: compute percentile from accumulated array
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v)
        FROM unnest($1) AS v
    ),
    INITCOND = '{}'
);

SELECT department_id, median(salary) AS median_salary
FROM employees GROUP BY department_id;
```

## Functions with Default Parameters

```sql
-- PostgreSQL: default parameter values
CREATE OR REPLACE FUNCTION search_employees(
    p_department_id INTEGER DEFAULT NULL,
    p_min_salary    NUMERIC DEFAULT NULL,
    p_status        TEXT DEFAULT 'active',
    p_limit         INTEGER DEFAULT 50
) RETURNS SETOF employees
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM employees
    WHERE (p_department_id IS NULL OR department_id = p_department_id)
      AND (p_min_salary IS NULL OR salary >= p_min_salary)
      AND status = p_status
    ORDER BY last_name, first_name
    LIMIT p_limit;
END;
$$;

-- Call with named parameters (PostgreSQL)
SELECT * FROM search_employees(p_min_salary => 80000, p_limit => 10);
SELECT * FROM search_employees(p_department_id => 5);
```

## Error Handling in Functions

```sql
-- PostgreSQL: raise exceptions with context
CREATE OR REPLACE FUNCTION safe_divide(p_numerator NUMERIC, p_denominator NUMERIC)
RETURNS NUMERIC
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF p_denominator = 0 THEN
        RAISE EXCEPTION 'Division by zero: % / %', p_numerator, p_denominator
            USING HINT = 'Ensure denominator is non-zero before calling safe_divide',
                  ERRCODE = '22012';
    END IF;
    RETURN ROUND(p_numerator / p_denominator, 6);
END;
$$;

-- Return NULL instead of raising (sometimes preferable)
CREATE OR REPLACE FUNCTION safe_divide_null(p_numerator NUMERIC, p_denominator NUMERIC)
RETURNS NUMERIC
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_denominator = 0 THEN NULL
                ELSE ROUND(p_numerator / p_denominator, 6) END;
$$;
```

## Performance Considerations

```sql
-- SQL-language functions are inlined by PostgreSQL's optimizer
-- when they meet certain criteria. This is MUCH faster.

-- GOOD: inlineable (SQL language, single SELECT, no side effects)
CREATE FUNCTION get_full_name(p_first TEXT, p_last TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT p_first || ' ' || p_last;
$$;

-- NOT inlineable (PL/pgSQL requires function call overhead per row)
CREATE FUNCTION get_full_name_plpgsql(p_first TEXT, p_last TEXT)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN p_first || ' ' || p_last;
END;
$$;

-- For large tables, the inlined version can be 10-50x faster.
-- Rule of thumb: use LANGUAGE sql when possible, plpgsql when you need
-- control flow (IF, LOOP, EXCEPTION handling).
```

## Function Overloading (PostgreSQL)

```sql
-- PostgreSQL supports function overloading: same name, different argument types
CREATE FUNCTION format_value(p_val INTEGER) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$ SELECT p_val::TEXT; $$;

CREATE FUNCTION format_value(p_val NUMERIC) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$ SELECT TO_CHAR(p_val, 'FM999,999,990.00'); $$;

CREATE FUNCTION format_value(p_val DATE) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$ SELECT TO_CHAR(p_val, 'YYYY-MM-DD'); $$;

-- Dispatches automatically: format_value(42) vs format_value(1234.56)
```
