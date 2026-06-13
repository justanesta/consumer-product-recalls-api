# JOIN Patterns

## JOIN Types Decision Matrix

| Join Type | Use When | Result | NULL Behavior |
|-----------|----------|--------|---------------|
| **INNER JOIN** | Only want matching rows | Intersection of both tables | Excludes non-matches |
| **LEFT JOIN** | Want all from left + matches from right | All left rows + matching right | NULL for non-matching right |
| **RIGHT JOIN** | Want all from right + matches from left | All right rows + matching left | NULL for non-matching left |
| **FULL OUTER JOIN** | Want all rows from both tables | Union of both tables | NULL for non-matches on either side |
| **CROSS JOIN** | Want all combinations (cartesian product) | Every row from left × every row from right | N/A |

## INNER JOIN

```sql
-- Only customers who have placed orders
SELECT 
    c.customer_id,
    c.customer_name,
    c.email,
    o.order_id,
    o.order_date,
    o.total_amount
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_date >= '2024-01-01'
ORDER BY o.order_date DESC;

-- Multiple conditions in join
SELECT 
    o.order_id,
    o.order_date,
    s.shipment_date,
    s.tracking_number
FROM orders o
INNER JOIN shipments s 
    ON o.order_id = s.order_id 
    AND o.warehouse_id = s.warehouse_id
WHERE s.status = 'delivered';
```

## LEFT JOIN

```sql
-- All customers with their orders (if any)
SELECT 
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_date,
    o.total_amount
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
ORDER BY c.customer_name;

-- Find customers who have NEVER ordered
SELECT 
    c.customer_id,
    c.customer_name,
    c.email,
    c.registration_date
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_id IS NULL;  -- No orders found

-- Find customers with no recent orders (last 90 days)
SELECT 
    c.customer_id,
    c.customer_name,
    MAX(o.order_date) AS last_order_date
FROM customers c
LEFT JOIN orders o 
    ON c.customer_id = o.customer_id 
    AND o.order_date >= CURRENT_DATE - INTERVAL '90 days'
WHERE c.status = 'active'
GROUP BY c.customer_id, c.customer_name
HAVING MAX(o.order_date) IS NULL;
```

## Multiple Table Joins

```sql
-- Chain joins for related data
SELECT 
    c.customer_name,
    o.order_id,
    o.order_date,
    p.product_name,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price AS line_total,
    cat.category_name
FROM customers c
INNER JOIN orders o ON o.customer_id = c.customer_id
INNER JOIN order_items oi ON oi.order_id = o.order_id
INNER JOIN products p ON p.product_id = oi.product_id
INNER JOIN categories cat ON cat.category_id = p.category_id
WHERE o.order_date >= '2024-01-01'
  AND c.country = 'USA'
ORDER BY o.order_date DESC, o.order_id;

-- Mix INNER and LEFT joins
SELECT 
    c.customer_name,
    o.order_id,
    o.total_amount,
    s.shipment_date,
    s.tracking_number,
    r.rating,
    r.review_text
FROM customers c
INNER JOIN orders o ON o.customer_id = c.customer_id
LEFT JOIN shipments s ON s.order_id = o.order_id
LEFT JOIN reviews r ON r.order_id = o.order_id
WHERE o.order_date >= '2024-01-01';
-- Returns all orders, with shipment and review if available
```

## Self Joins

```sql
-- Employees and their managers
SELECT 
    e.employee_id,
    e.employee_name AS employee,
    e.title,
    m.employee_name AS manager,
    m.title AS manager_title
FROM employees e
LEFT JOIN employees m ON e.manager_id = m.employee_id
ORDER BY m.employee_name NULLS FIRST, e.employee_name;

-- Find customers in the same city (pairwise)
SELECT 
    c1.customer_name AS customer1,
    c2.customer_name AS customer2,
    c1.city,
    c1.state
FROM customers c1
INNER JOIN customers c2 
    ON c1.city = c2.city 
    AND c1.state = c2.state
    AND c1.customer_id < c2.customer_id  -- Avoid duplicates and self-match
ORDER BY c1.city, c1.customer_name;

-- Hierarchical product categories
SELECT 
    child.category_id,
    child.category_name,
    parent.category_name AS parent_category
FROM categories child
LEFT JOIN categories parent ON child.parent_category_id = parent.category_id
ORDER BY parent.category_name NULLS FIRST, child.category_name;
```

## Join Conditions vs WHERE Filters

```sql
-- Critical difference for outer joins!

-- CORRECT - Filter customers in WHERE (filters final result)
SELECT c.customer_name, o.order_id
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
WHERE c.status = 'active';
-- Returns all active customers (with orders if they exist)

-- INCORRECT - Filter in ON clause  
SELECT c.customer_name, o.order_id
FROM customers c
LEFT JOIN orders o 
    ON c.customer_id = o.customer_id 
    AND c.status = 'active';  -- WRONG for LEFT JOIN
-- Returns ALL customers, but only shows orders for active ones
-- Inactive customers still appear with NULL orders

-- For INNER JOIN, these are equivalent:
SELECT *
FROM products p
INNER JOIN categories c 
    ON p.category_id = c.category_id 
    AND p.price > 100;

SELECT *
FROM products p
INNER JOIN categories c ON p.category_id = c.category_id
WHERE p.price > 100;
```

## CROSS JOIN

```sql
-- Every combination (cartesian product)
SELECT 
    p.product_name,
    s.size_name,
    c.color_name
FROM products p
CROSS JOIN sizes s
CROSS JOIN colors c
WHERE p.category = 'Clothing';
-- Generates all possible product/size/color combinations

-- Generate date series with hours
SELECT 
    d.date,
    h.hour,
    d.date + (h.hour || ' hours')::INTERVAL AS datetime
FROM 
    generate_series('2024-01-01'::date, '2024-01-31'::date, '1 day'::interval) d(date)
CROSS JOIN 
    generate_series(0, 23) h(hour);
```

## Range Joins (Non-Equality)

```sql
-- Join on date ranges
SELECT 
    s.sale_date,
    s.amount,
    s.currency,
    r.exchange_rate,
    s.amount * r.exchange_rate AS amount_usd
FROM sales s
INNER JOIN exchange_rates r
    ON s.currency = r.currency
    AND s.sale_date BETWEEN r.effective_date AND r.expiration_date;

-- Join on overlapping time periods
SELECT 
    p1.project_name AS project1,
    p2.project_name AS project2,
    p1.start_date,
    p1.end_date,
    p2.start_date AS overlap_start,
    p2.end_date AS overlap_end
FROM projects p1
INNER JOIN projects p2
    ON p1.project_id < p2.project_id
    AND p1.start_date <= p2.end_date
    AND p1.end_date >= p2.start_date
ORDER BY p1.start_date;
```

## Performance Tips

```sql
-- GOOD: Join on indexed columns
SELECT *
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id;
-- Fast if customer_id is indexed in both tables

-- BAD: Join on computed values (can't use indexes)
SELECT *
FROM orders o
INNER JOIN customers c ON LOWER(o.customer_email) = LOWER(c.email);
-- Must compute for every row, can't use indexes

-- GOOD: Normalize and index properly
-- Store emails in lowercase, create index, then:
SELECT *
FROM orders o
INNER JOIN customers c ON o.customer_email = c.email;

-- Join order matters (database optimizes, but be aware)
-- Start with most filtered table
SELECT *
FROM (
    SELECT * FROM large_table WHERE specific_filter
) filtered
INNER JOIN another_table ON filtered.id = another_table.id;
```

## Anti-Patterns

```sql
-- BAD: Implicit join (old style, confusing)
SELECT c.customer_name, o.order_id
FROM customers c, orders o
WHERE c.customer_id = o.customer_id;

-- GOOD: Explicit JOIN
SELECT c.customer_name, o.order_id
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id;

-- BAD: OR in JOIN condition
SELECT *
FROM table_a a
LEFT JOIN table_b b ON a.id = b.id OR a.alt_id = b.id;

-- BETTER: Separate with UNION
SELECT * FROM table_a a LEFT JOIN table_b b ON a.id = b.id
UNION
SELECT * FROM table_a a LEFT JOIN table_b b ON a.alt_id = b.id;
```
