# Subquery Patterns

## Subquery in WHERE Clause

```sql
-- Scalar subquery (returns single value)
SELECT product_name, price
FROM products
WHERE price > (
    SELECT AVG(price) FROM products
);

-- IN subquery (returns multiple values)
SELECT customer_name, email
FROM customers
WHERE customer_id IN (
    SELECT DISTINCT customer_id
    FROM orders
    WHERE order_date >= '2024-01-01'
);

-- Multiple conditions with subqueries
SELECT product_name, price
FROM products
WHERE category_id IN (SELECT category_id FROM trending_categories)
  AND price < (SELECT AVG(price) FROM products)
  AND manufacturer_id NOT IN (SELECT id FROM blacklisted_manufacturers);
```

## Subquery in FROM (Derived Table)

```sql
-- Subquery as table source
SELECT 
    category,
    avg_price,
    product_count,
    CASE 
        WHEN avg_price > 100 THEN 'Premium'
        WHEN avg_price > 50 THEN 'Standard'
        ELSE 'Budget'
    END AS price_tier
FROM (
    SELECT 
        category,
        AVG(price) AS avg_price,
        COUNT(*) AS product_count
    FROM products
    WHERE status = 'active'
    GROUP BY category
) AS category_stats
WHERE product_count > 10
ORDER BY avg_price DESC;

-- Multiple derived tables with joins
SELECT 
    cs.category,
    cs.product_count,
    ss.total_sales,
    ss.total_sales / cs.product_count AS sales_per_product
FROM (
    SELECT category, COUNT(*) AS product_count
    FROM products
    GROUP BY category
) AS cs
INNER JOIN (
    SELECT 
        p.category,
        SUM(oi.quantity * oi.unit_price) AS total_sales
    FROM order_items oi
    JOIN products p ON oi.product_id = p.product_id
    GROUP BY p.category
) AS ss ON cs.category = ss.category;
```

## Correlated Subquery

```sql
-- Subquery references outer query (runs once per outer row)
SELECT 
    e.employee_name,
    e.salary,
    e.department_id,
    (SELECT AVG(salary) 
     FROM employees e2 
     WHERE e2.department_id = e.department_id) AS dept_avg_salary,
    e.salary - (
        SELECT AVG(salary) 
        FROM employees e3 
        WHERE e3.department_id = e.department_id
    ) AS salary_vs_dept_avg
FROM employees e
ORDER BY department_id, salary DESC;

-- Find employees with above-average salary for their department
SELECT 
    employee_name,
    salary,
    department_id
FROM employees e1
WHERE salary > (
    SELECT AVG(salary)
    FROM employees e2
    WHERE e2.department_id = e1.department_id
);

-- Find customers with above-average order totals
SELECT 
    c.customer_name,
    (SELECT AVG(total_amount) 
     FROM orders o 
     WHERE o.customer_id = c.customer_id) AS avg_order_value
FROM customers c
WHERE (
    SELECT AVG(total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
) > (SELECT AVG(total_amount) FROM orders);
```

## EXISTS vs IN

```sql
-- EXISTS (stops at first match - often faster)
SELECT customer_name, email
FROM customers c
WHERE EXISTS (
    SELECT 1  -- Value doesn't matter, just checks existence
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_date >= '2024-01-01'
);

-- IN (evaluates entire subquery)
SELECT customer_name, email
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE order_date >= '2024-01-01'
);

-- NOT EXISTS (handles NULLs correctly)
SELECT customer_name, email
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);

-- Performance: EXISTS typically better when:
-- - Subquery returns large result set
-- - Only checking existence (don't need values)
-- - Using correlated subquery
```

## Subquery in SELECT

```sql
-- Scalar subqueries in SELECT list
SELECT 
    p.product_name,
    p.price,
    p.category_id,
    (SELECT category_name FROM categories c WHERE c.category_id = p.category_id) AS category_name,
    (SELECT AVG(price) FROM products) AS overall_avg_price,
    (SELECT AVG(price) FROM products p2 WHERE p2.category_id = p.category_id) AS category_avg_price,
    (SELECT COUNT(*) FROM order_items oi WHERE oi.product_id = p.product_id) AS times_ordered
FROM products p
WHERE p.status = 'active'
ORDER BY p.product_name;

-- Multiple correlated subqueries
SELECT 
    c.customer_id,
    c.customer_name,
    (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.customer_id) AS total_orders,
    (SELECT SUM(total_amount) FROM orders o WHERE o.customer_id = c.customer_id) AS lifetime_value,
    (SELECT MAX(order_date) FROM orders o WHERE o.customer_id = c.customer_id) AS last_order_date
FROM customers c
WHERE c.status = 'active'
ORDER BY lifetime_value DESC NULLS LAST;
```

## ANY and ALL

```sql
-- ANY: True if comparison is true for ANY value in list
SELECT product_name, price
FROM products
WHERE price > ANY (
    SELECT price 
    FROM products 
    WHERE category = 'Electronics'
);
-- Returns products more expensive than at least one electronics item

-- ALL: True if comparison is true for ALL values in list
SELECT product_name, price
FROM products
WHERE price > ALL (
    SELECT price 
    FROM products 
    WHERE category = 'Electronics'
);
-- Returns products more expensive than all electronics items

-- Equivalent expressions:
-- price > ANY (subquery) = price > MIN(subquery)
-- price > ALL (subquery) = price > MAX(subquery)

-- SOME is synonym for ANY
WHERE quantity > SOME (SELECT avg_quantity FROM category_stats);
```

## Subquery vs JOIN Performance

```sql
-- Often better to use JOIN instead of subquery

-- Subquery approach (can be slow with large datasets):
SELECT *
FROM customers
WHERE customer_id IN (
    SELECT customer_id 
    FROM orders 
    WHERE order_date >= '2024-01-01'
);

-- JOIN approach (often faster):
SELECT DISTINCT c.*
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_date >= '2024-01-01';

-- However, EXISTS can be faster than JOIN for existence checks:
SELECT c.*
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o 
    WHERE o.customer_id = c.customer_id 
    AND o.order_date >= '2024-01-01'
);
-- Stops searching once first match found
```

## Lateral Subqueries (PostgreSQL, SQL Server)

```sql
-- LATERAL allows subquery to reference previous FROM items
SELECT 
    c.customer_name,
    recent.order_date,
    recent.total_amount
FROM customers c
CROSS JOIN LATERAL (
    SELECT order_date, total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY order_date DESC
    LIMIT 3
) AS recent
WHERE c.status = 'active';

-- SQL Server uses CROSS APPLY
SELECT 
    c.customer_name,
    recent.order_date,
    recent.total_amount
FROM customers c
CROSS APPLY (
    SELECT TOP 3 order_date, total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY order_date DESC
) AS recent
WHERE c.status = 'active';
```
