# SELECT Patterns

## Column Selection and Aliases

```sql
-- Explicit column selection (RECOMMENDED)
SELECT 
    customer_id,
    first_name,
    last_name,
    email,
    created_date
FROM customers
WHERE status = 'active';

-- SELECT * (AVOID in production code)
SELECT * FROM customers;  
-- Problems: Returns unnecessary data, breaks when schema changes, unclear intent

-- Column aliases (use AS for clarity)
SELECT 
    customer_id AS id,
    first_name AS fname,
    last_name AS lname,
    first_name || ' ' || last_name AS full_name,  -- PostgreSQL
    CONCAT(first_name, ' ', last_name) AS full_name  -- MySQL, SQL Server
FROM customers;

-- Aliases with spaces (requires quotes)
SELECT 
    total_amount AS "Order Total",
    order_date AS "Date Placed",
    customer_name AS "Customer Name"
FROM orders;
```

## Calculated Columns

```sql
-- Arithmetic operations
SELECT 
    product_name,
    price,
    price * 1.08 AS price_with_tax,
    price * 0.85 AS sale_price,
    ROUND(price * 1.08, 2) AS price_rounded
FROM products;

-- String operations
SELECT 
    first_name,
    last_name,
    first_name || ' ' || last_name AS full_name,  -- PostgreSQL
    CONCAT(first_name, ' ', last_name) AS full_name,  -- MySQL
    UPPER(email) AS email_upper,
    SUBSTRING(phone, 1, 3) AS area_code,
    LENGTH(description) AS desc_length
FROM customers;

-- Date calculations
SELECT 
    order_date,
    order_date + INTERVAL '7 days' AS expected_delivery,  -- PostgreSQL
    DATE_ADD(order_date, INTERVAL 7 DAY) AS expected_delivery,  -- MySQL
    DATEADD(day, 7, order_date) AS expected_delivery,  -- SQL Server
    EXTRACT(YEAR FROM order_date) AS order_year,
    EXTRACT(MONTH FROM order_date) AS order_month
FROM orders;

-- Conditional calculations
SELECT 
    product_name,
    price,
    quantity,
    price * quantity AS subtotal,
    CASE 
        WHEN quantity >= 100 THEN price * 0.90  -- 10% bulk discount
        WHEN quantity >= 50 THEN price * 0.95   -- 5% discount
        ELSE price
    END * quantity AS total_after_discount
FROM order_items;
```

## DISTINCT Usage

```sql
-- Simple DISTINCT (unique values)
SELECT DISTINCT country
FROM customers
ORDER BY country;

-- DISTINCT with multiple columns (unique combinations)
SELECT DISTINCT country, city
FROM customers
ORDER BY country, city;

-- DISTINCT in aggregate (count unique)
SELECT 
    category,
    COUNT(*) AS total_products,
    COUNT(DISTINCT manufacturer) AS unique_manufacturers,
    COUNT(DISTINCT CASE WHEN in_stock THEN manufacturer END) AS in_stock_manufacturers
FROM products
GROUP BY category;

-- DISTINCT ON (PostgreSQL only - first row per group)
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_date,
    total_amount
FROM orders
ORDER BY customer_id, order_date DESC;
-- Returns most recent order per customer
```

## DISTINCT vs GROUP BY

```sql
-- These produce the same result but different approaches:

-- DISTINCT (simpler for deduplication)
SELECT DISTINCT category
FROM products;

-- GROUP BY (use when you need aggregation)
SELECT category
FROM products
GROUP BY category;

-- GROUP BY is necessary with aggregates
SELECT 
    category,
    COUNT(*) AS product_count,
    AVG(price) AS avg_price,
    MAX(price) AS max_price
FROM products
GROUP BY category;
```

## Pagination Across Databases

```sql
-- PostgreSQL, MySQL, SQLite
SELECT *
FROM products
ORDER BY product_id
LIMIT 20 OFFSET 40;  -- Page 3 (items 41-60)

-- SQL Server (2012+)
SELECT *
FROM products
ORDER BY product_id
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;

-- Older SQL Server (before 2012)
WITH numbered AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (ORDER BY product_id) AS rn
    FROM products
)
SELECT *
FROM numbered
WHERE rn BETWEEN 41 AND 60;

-- Keyset pagination (efficient for large offsets)
-- Instead of OFFSET 1000000, use:
SELECT *
FROM products
WHERE product_id > @last_id_from_previous_page
ORDER BY product_id
LIMIT 20;
```

## Table and Column Prefixes

```sql
-- Without prefixes (ambiguous, error-prone)
SELECT 
    id,
    name,
    order_date
FROM customers
JOIN orders ON customer_id = id;  -- Which id? Unclear!

-- With table aliases (RECOMMENDED)
SELECT 
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_date,
    o.total_amount
FROM customers c
INNER JOIN orders o ON o.customer_id = c.customer_id
WHERE c.status = 'active'
ORDER BY o.order_date DESC;

-- Complex query with multiple joins
SELECT 
    c.customer_name,
    o.order_id,
    oi.product_id,
    p.product_name,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price AS line_total
FROM customers c
INNER JOIN orders o ON o.customer_id = c.customer_id
INNER JOIN order_items oi ON oi.order_id = o.order_id
INNER JOIN products p ON p.product_id = oi.product_id
WHERE o.order_date >= '2024-01-01'
ORDER BY o.order_date DESC, o.order_id, oi.line_number;
```

## Performance Considerations

```sql
-- BAD: SELECT * loads unnecessary columns
SELECT * FROM large_table WHERE id = 123;
-- Loads all columns even if you only need a few

-- GOOD: Select only needed columns
SELECT id, name, email, status
FROM large_table
WHERE id = 123;

-- BAD: No filtering on large tables
SELECT customer_name, email
FROM customers;  -- Returns millions of rows

-- GOOD: Always filter when possible
SELECT customer_name, email
FROM customers
WHERE status = 'active'
  AND created_date >= '2024-01-01'
LIMIT 1000;

-- BAD: Repeated calculation
SELECT 
    price * quantity AS line_total,
    (price * quantity) * 0.08 AS tax,
    (price * quantity) + ((price * quantity) * 0.08) AS final_total
FROM order_items;

-- BETTER: Calculate once with CTE or subquery
WITH calculated AS (
    SELECT 
        *,
        price * quantity AS line_total
    FROM order_items
)
SELECT 
    line_total,
    line_total * 0.08 AS tax,
    line_total * 1.08 AS final_total
FROM calculated;
```
