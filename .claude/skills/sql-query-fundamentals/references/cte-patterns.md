# CTE (Common Table Expression) Patterns

## Basic CTE Syntax

```sql
-- Single CTE
WITH active_customers AS (
    SELECT 
        customer_id,
        customer_name,
        email,
        total_purchases
    FROM customers
    WHERE status = 'active'
      AND last_order_date >= CURRENT_DATE - INTERVAL '90 days'
)
SELECT 
    ac.customer_name,
    ac.email,
    COUNT(o.order_id) AS recent_order_count,
    SUM(o.total_amount) AS recent_total_spent,
    ac.total_purchases AS lifetime_total
FROM active_customers ac
LEFT JOIN orders o 
    ON ac.customer_id = o.customer_id
    AND o.order_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY ac.customer_id, ac.customer_name, ac.email, ac.total_purchases
HAVING COUNT(o.order_id) > 0
ORDER BY recent_total_spent DESC;
```

## Multiple CTEs

```sql
-- Chain multiple CTEs (comma-separated)
WITH 
    -- First CTE: Calculate monthly totals
    monthly_sales AS (
        SELECT 
            DATE_TRUNC('month', order_date) AS month,
            SUM(total_amount) AS revenue,
            COUNT(*) AS order_count,
            COUNT(DISTINCT customer_id) AS unique_customers
        FROM orders
        WHERE order_date >= '2024-01-01'
        GROUP BY DATE_TRUNC('month', order_date)
    ),
    -- Second CTE: Add growth calculations
    sales_with_growth AS (
        SELECT 
            month,
            revenue,
            order_count,
            unique_customers,
            LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
            revenue - LAG(revenue) OVER (ORDER BY month) AS revenue_growth,
            LAG(unique_customers) OVER (ORDER BY month) AS prev_month_customers
        FROM monthly_sales
    ),
    -- Third CTE: Categorize performance
    categorized_months AS (
        SELECT 
            *,
            CASE 
                WHEN revenue_growth > prev_month_revenue * 0.1 THEN 'Strong Growth'
                WHEN revenue_growth > 0 THEN 'Moderate Growth'
                WHEN revenue_growth IS NULL THEN 'First Month'
                ELSE 'Decline'
            END AS trend,
            ROUND(100.0 * revenue_growth / NULLIF(prev_month_revenue, 0), 2) AS growth_pct
        FROM sales_with_growth
    )
SELECT * 
FROM categorized_months
ORDER BY month;
```

## CTE vs Subquery Comparison

```sql
-- Complex query with nested subqueries (hard to read)
SELECT 
    category,
    avg_price,
    tier,
    product_count
FROM (
    SELECT 
        category,
        avg_price,
        product_count,
        CASE 
            WHEN avg_price > 100 THEN 'Premium'
            WHEN avg_price > 50 THEN 'Standard'
            ELSE 'Budget'
        END AS tier
    FROM (
        SELECT 
            category,
            AVG(price) AS avg_price,
            COUNT(*) AS product_count
        FROM products
        WHERE status = 'active'
        GROUP BY category
    ) AS cat_stats
) AS cat_tiers
WHERE tier = 'Premium'
ORDER BY avg_price DESC;

-- Same query with CTEs (much more readable)
WITH 
    category_stats AS (
        SELECT 
            category,
            AVG(price) AS avg_price,
            COUNT(*) AS product_count
        FROM products
        WHERE status = 'active'
        GROUP BY category
    ),
    category_tiers AS (
        SELECT 
            category,
            avg_price,
            product_count,
            CASE 
                WHEN avg_price > 100 THEN 'Premium'
                WHEN avg_price > 50 THEN 'Standard'
                ELSE 'Budget'
            END AS tier
        FROM category_stats
    )
SELECT 
    category,
    avg_price,
    tier,
    product_count
FROM category_tiers
WHERE tier = 'Premium'
ORDER BY avg_price DESC;
```

## Recursive CTEs

```sql
-- Employee hierarchy (reporting structure)
WITH RECURSIVE employee_hierarchy AS (
    -- Base case: Top-level employees (no manager)
    SELECT 
        employee_id,
        employee_name,
        manager_id,
        title,
        0 AS level,
        employee_name AS path
    FROM employees
    WHERE manager_id IS NULL
    
    UNION ALL
    
    -- Recursive case: Employees with managers
    SELECT 
        e.employee_id,
        e.employee_name,
        e.manager_id,
        e.title,
        eh.level + 1,
        eh.path || ' > ' || e.employee_name
    FROM employees e
    INNER JOIN employee_hierarchy eh 
        ON e.manager_id = eh.employee_id
    WHERE eh.level < 10  -- Prevent infinite loops
)
SELECT 
    employee_name,
    title,
    level,
    path AS reporting_chain
FROM employee_hierarchy
ORDER BY path;

-- Generate date series
WITH RECURSIVE date_series AS (
    SELECT DATE '2024-01-01' AS date
    UNION ALL
    SELECT date + INTERVAL '1 day'
    FROM date_series
    WHERE date < DATE '2024-12-31'
)
SELECT 
    date,
    EXTRACT(DOW FROM date) AS day_of_week,
    TO_CHAR(date, 'Day') AS day_name
FROM date_series
WHERE EXTRACT(DOW FROM date) NOT IN (0, 6)  -- Weekdays only
ORDER BY date;

-- Generate number sequence
WITH RECURSIVE numbers AS (
    SELECT 1 AS n
    UNION ALL
    SELECT n + 1 
    FROM numbers 
    WHERE n < 100
)
SELECT n, n * n AS square, n * n * n AS cube
FROM numbers;
```

## Recursive CTE for Graph Traversal

```sql
-- Find all categories and subcategories (hierarchical tree)
WITH RECURSIVE category_tree AS (
    -- Root categories (no parent)
    SELECT 
        category_id,
        category_name,
        parent_category_id,
        category_name AS path,
        0 AS depth,
        ARRAY[category_id] AS id_path  -- Track path to detect cycles
    FROM categories
    WHERE parent_category_id IS NULL
    
    UNION ALL
    
    -- Child categories
    SELECT 
        c.category_id,
        c.category_name,
        c.parent_category_id,
        ct.path || ' > ' || c.category_name,
        ct.depth + 1,
        ct.id_path || c.category_id
    FROM categories c
    INNER JOIN category_tree ct 
        ON c.parent_category_id = ct.category_id
    WHERE NOT (c.category_id = ANY(ct.id_path))  -- Detect cycles
      AND ct.depth < 20  -- Safety limit
)
SELECT 
    category_id,
    category_name,
    depth,
    path
FROM category_tree
ORDER BY path;
```

## CTE for Data Transformation Pipeline

```sql
-- Multi-stage data cleaning and transformation
WITH 
    -- Stage 1: Initial filtering
    raw_data AS (
        SELECT *
        FROM customer_imports
        WHERE imported_date = CURRENT_DATE
    ),
    -- Stage 2: Clean and normalize
    cleaned_data AS (
        SELECT 
            customer_id,
            TRIM(UPPER(email)) AS email,
            CASE 
                WHEN country IN ('US', 'USA', 'United States') THEN 'United States'
                WHEN country IN ('UK', 'United Kingdom', 'GB') THEN 'United Kingdom'
                ELSE INITCAP(country)
            END AS country,
            COALESCE(phone_mobile, phone_home) AS primary_phone
        FROM raw_data
        WHERE email IS NOT NULL
          AND email LIKE '%@%'
    ),
    -- Stage 3: Deduplicate
    deduplicated AS (
        SELECT DISTINCT ON (email)
            *,
            ROW_NUMBER() OVER (PARTITION BY email ORDER BY customer_id) AS rn
        FROM cleaned_data
    ),
    -- Stage 4: Enrich with order data
    enriched AS (
        SELECT 
            d.*,
            COUNT(o.order_id) AS order_count,
            COALESCE(SUM(o.total_amount), 0) AS lifetime_value,
            MAX(o.order_date) AS last_order_date
        FROM deduplicated d
        LEFT JOIN orders o ON d.customer_id = o.customer_id
        WHERE d.rn = 1
        GROUP BY d.customer_id, d.email, d.country, d.primary_phone, d.rn
    )
SELECT 
    customer_id,
    email,
    country,
    primary_phone,
    order_count,
    lifetime_value,
    last_order_date,
    CASE 
        WHEN order_count >= 10 THEN 'VIP'
        WHEN order_count >= 5 THEN 'Regular'
        WHEN order_count > 0 THEN 'Occasional'
        ELSE 'Never Ordered'
    END AS customer_segment
FROM enriched;
```

## Materialized CTEs (PostgreSQL 12+)

```sql
-- Force materialization (compute once, reuse)
WITH monthly_totals AS MATERIALIZED (
    SELECT 
        DATE_TRUNC('month', order_date) AS month,
        SUM(total_amount) AS revenue
    FROM orders  -- Large table
    GROUP BY DATE_TRUNC('month', order_date)
)
SELECT * 
FROM monthly_totals 
WHERE revenue > 100000
UNION ALL
SELECT * 
FROM monthly_totals 
WHERE revenue < 10000;
-- CTE computed once, used twice

-- Prevent materialization (inline the query)
WITH small_filter AS NOT MATERIALIZED (
    SELECT * 
    FROM products 
    WHERE category = 'Electronics'
)
SELECT * FROM small_filter WHERE price > 100;
```

## Performance Considerations

```sql
-- CTEs are evaluated differently across databases:
-- PostgreSQL < 12: Always materialized
-- PostgreSQL 12+: Optimizer decides (can control with MATERIALIZED/NOT MATERIALIZED)
-- SQL Server: Usually inlined
-- MySQL 8.0+: Can be materialized or inlined

-- If CTE is referenced multiple times, materialization helps:
WITH expensive_calculation AS (
    SELECT 
        customer_id,
        complex_calculation(data) AS result
    FROM huge_table
    WHERE complex_condition
)
SELECT * FROM expensive_calculation WHERE result > 100
UNION ALL
SELECT * FROM expensive_calculation WHERE result < 10;

-- If referenced once, inlining usually better:
WITH simple_filter AS (
    SELECT * FROM table WHERE simple_condition
)
SELECT * FROM simple_filter WHERE another_condition;
-- Might be better as single query with both conditions
```
