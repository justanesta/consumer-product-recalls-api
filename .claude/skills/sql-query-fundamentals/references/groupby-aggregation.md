# GROUP BY and Aggregation

## Basic Aggregation Functions

```sql
-- Common aggregates
SELECT 
    COUNT(*) AS total_rows,
    COUNT(column_name) AS non_null_count,  -- Excludes NULLs
    COUNT(DISTINCT customer_id) AS unique_customers,
    SUM(amount) AS total_amount,
    AVG(price) AS average_price,
    MIN(order_date) AS first_order,
    MAX(order_date) AS last_order,
    STDDEV(price) AS price_std_dev,
    VARIANCE(price) AS price_variance
FROM orders;
```

## GROUP BY Single Column

```sql
-- Basic grouping
SELECT 
    category,
    COUNT(*) AS product_count,
    AVG(price) AS avg_price,
    MIN(price) AS min_price,
    MAX(price) AS max_price,
    SUM(price * quantity_in_stock) AS inventory_value
FROM products
WHERE price > 0
GROUP BY category
ORDER BY product_count DESC;
```

## GROUP BY Multiple Columns

```sql
-- Multiple grouping levels
SELECT 
    country,
    city,
    COUNT(*) AS customer_count,
    SUM(total_purchases) AS revenue,
    AVG(total_purchases) AS avg_customer_value
FROM customers
WHERE status = 'active'
GROUP BY country, city
ORDER BY country, revenue DESC;

-- Date-based grouping
SELECT 
    DATE_TRUNC('month', order_date) AS month,  -- PostgreSQL
    DATE_FORMAT(order_date, '%Y-%m') AS month,  -- MySQL
    FORMAT(order_date, 'yyyy-MM') AS month,  -- SQL Server
    COUNT(*) AS order_count,
    SUM(total_amount) AS monthly_revenue,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM orders
WHERE order_date >= '2024-01-01'
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month;
```

## HAVING Clause

```sql
-- HAVING filters after aggregation (WHERE filters before)
SELECT 
    category,
    COUNT(*) AS product_count,
    AVG(price) AS avg_price
FROM products
WHERE price > 0  -- Filter rows before grouping
GROUP BY category
HAVING COUNT(*) > 10  -- Filter groups after aggregation
  AND AVG(price) < 100
ORDER BY product_count DESC;

-- Find high-value customers
SELECT 
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS lifetime_value,
    AVG(total_amount) AS avg_order_value
FROM orders
WHERE status = 'completed'
GROUP BY customer_id
HAVING COUNT(*) >= 5 
  AND SUM(total_amount) > 10000
ORDER BY lifetime_value DESC;
```

## Conditional Aggregation

```sql
-- COUNT with CASE (count different categories)
SELECT 
    category,
    COUNT(*) AS total_products,
    COUNT(CASE WHEN price < 20 THEN 1 END) AS budget_count,
    COUNT(CASE WHEN price BETWEEN 20 AND 100 THEN 1 END) AS mid_range_count,
    COUNT(CASE WHEN price > 100 THEN 1 END) AS premium_count,
    SUM(CASE WHEN in_stock THEN 1 ELSE 0 END) AS in_stock_count
FROM products
GROUP BY category;

-- SUM with CASE (conditional sums)
SELECT 
    DATE_TRUNC('day', order_date) AS day,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'completed' THEN total_amount ELSE 0 END) AS completed_revenue,
    SUM(CASE WHEN status = 'refunded' THEN total_amount ELSE 0 END) AS refunded_amount,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count
FROM orders
WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', order_date)
ORDER BY day;
```

## DISTINCT in Aggregations

```sql
-- Count unique values per group
SELECT 
    DATE_TRUNC('month', order_date) AS month,
    COUNT(*) AS total_orders,
    COUNT(DISTINCT customer_id) AS unique_customers,
    COUNT(DISTINCT product_id) AS unique_products,
    SUM(total_amount) AS revenue,
    SUM(total_amount) / COUNT(DISTINCT customer_id) AS revenue_per_customer
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_date >= '2024-01-01'
GROUP BY DATE_TRUNC('month', order_date);
```

## String Aggregation

```sql
-- PostgreSQL
SELECT 
    category,
    STRING_AGG(product_name, ', ' ORDER BY product_name) AS products,
    STRING_AGG(DISTINCT manufacturer, '; ') AS manufacturers
FROM products
GROUP BY category;

-- MySQL  
SELECT 
    category,
    GROUP_CONCAT(product_name ORDER BY product_name SEPARATOR ', ') AS products,
    GROUP_CONCAT(DISTINCT manufacturer SEPARATOR '; ') AS manufacturers
FROM products
GROUP BY category;

-- SQL Server
SELECT 
    category,
    STRING_AGG(product_name, ', ') WITHIN GROUP (ORDER BY product_name) AS products
FROM products
GROUP BY category;
```

## FILTER Clause (PostgreSQL 9.4+)

```sql
-- Cleaner alternative to CASE for conditional aggregation
SELECT 
    category,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE price < 20) AS budget_count,
    COUNT(*) FILTER (WHERE price BETWEEN 20 AND 100) AS mid_range,
    COUNT(*) FILTER (WHERE price > 100) AS premium_count,
    AVG(price) FILTER (WHERE in_stock = TRUE) AS avg_in_stock_price,
    SUM(quantity) FILTER (WHERE reorder_needed = TRUE) AS reorder_quantity
FROM products
GROUP BY category;
```

## GROUPING SETS (Advanced)

```sql
-- Multiple grouping levels in one query
SELECT 
    country,
    city,
    SUM(total_purchases) AS revenue,
    COUNT(*) AS customer_count
FROM customers
GROUP BY GROUPING SETS (
    (country, city),  -- City level
    (country),        -- Country level
    ()                -- Grand total
)
ORDER BY country NULLS LAST, city NULLS LAST;

-- ROLLUP (hierarchical totals)
SELECT 
    country,
    city,
    SUM(revenue) AS total_revenue
FROM sales
GROUP BY ROLLUP (country, city);

-- CUBE (all combinations)
SELECT 
    product_category,
    customer_segment,
    SUM(revenue) AS total_revenue
FROM sales
GROUP BY CUBE (product_category, customer_segment);
```

## Performance Tips

```sql
-- GOOD: Filter before aggregation when possible
SELECT 
    category,
    COUNT(*) AS active_count,
    AVG(price) AS avg_price
FROM products
WHERE status = 'active'  -- Filter reduces rows before grouping
GROUP BY category;

-- Index on grouped columns
-- CREATE INDEX idx_products_category ON products(category);

-- For large datasets, consider approximate aggregates
-- PostgreSQL HyperLogLog for approximate COUNT DISTINCT
SELECT 
    category,
    COUNT(*) AS total,
    COUNT(DISTINCT customer_id) AS exact_customers
FROM large_table
GROUP BY category;
```
