---
name: sql-query-fundamentals
description: |
  Core SQL query patterns for SELECT, JOINs, WHERE, GROUP BY, and subqueries. Use this
  skill when writing basic to intermediate SQL queries, need to understand join types,
  or work with filtering and aggregation. Covers SELECT fundamentals, all join types,
  subqueries, CTEs, CASE expressions, and common table operations.
---

# SQL Query Fundamentals

Essential SQL patterns for querying relational databases.

## Core Principles

1. **SELECT only what you need** - Avoid `SELECT *` in production
2. **Use explicit JOINs** - Never use implicit joins with WHERE
3. **Filter early** - Apply WHERE before GROUP BY when possible
4. **Use CTEs for clarity** - Make complex queries readable

## Basic SELECT Patterns

```sql
SELECT
    customer_id,
    first_name,
    last_name,
    email
FROM customers
WHERE status = 'active'
ORDER BY last_name, first_name;
```

See [select-patterns.md](references/select-patterns.md) for:
- Column aliases and calculated columns
- DISTINCT vs GROUP BY
- LIMIT/OFFSET pagination across databases
- Column selection best practices

## JOIN Types

```sql
-- INNER JOIN (only matching rows)
SELECT o.order_id, c.customer_name, o.order_date
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id;

-- LEFT JOIN + find unmatched rows
SELECT c.customer_id, c.customer_name
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_id IS NULL;
```

See [join-patterns.md](references/join-patterns.md) for:
- Join types decision matrix
- Multiple table joins and self joins
- Join conditions vs WHERE filters
- Range joins and CROSS JOINs

## WHERE Clause Patterns

```sql
WHERE age >= 18 AND age < 65
-- IN clause (better than multiple ORs)
WHERE country IN ('USA', 'Canada', 'Mexico')
-- BETWEEN for ranges
WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31'
-- NULL handling
WHERE COALESCE(mobile_phone, home_phone) IS NOT NULL
```

See [where-clause-patterns.md](references/where-clause-patterns.md) for:
- Operator precedence and pattern matching
- NULL handling strategies
- Performance considerations (sargable queries)

## GROUP BY and Aggregations

```sql
SELECT
    category,
    COUNT(*) as product_count,
    AVG(price) as avg_price,
    SUM(price * quantity) as total_revenue
FROM products
GROUP BY category
HAVING COUNT(*) > 5 AND SUM(price * quantity) > 1000
ORDER BY total_revenue DESC;
```

See [groupby-aggregation.md](references/groupby-aggregation.md) for:
- Common aggregate functions
- GROUP BY vs DISTINCT
- HAVING vs WHERE

## Subqueries

```sql
-- Correlated subquery: employees above department average
SELECT
    e.employee_name,
    e.salary,
    (SELECT AVG(salary)
     FROM employees e2
     WHERE e2.department_id = e.department_id) as dept_avg
FROM employees e
WHERE e.salary > (
    SELECT AVG(salary) FROM employees e3
    WHERE e3.department_id = e.department_id
);
```

See [subquery-patterns.md](references/subquery-patterns.md) for:
- Subquery types (scalar, column, row, table)
- Correlated vs non-correlated
- EXISTS vs IN performance
- When to use subquery vs JOIN

## Common Table Expressions (CTEs)

```sql
WITH
    high_value_orders AS (
        SELECT * FROM orders WHERE total_amount > 1000
    ),
    vip_customers AS (
        SELECT customer_id, COUNT(*) as high_value_count
        FROM high_value_orders
        GROUP BY customer_id
        HAVING COUNT(*) >= 3
    )
SELECT c.customer_name, c.email, vc.high_value_count
FROM customers c
INNER JOIN vip_customers vc ON c.customer_id = vc.customer_id;
```

See [cte-patterns.md](references/cte-patterns.md) for:
- CTE vs subquery trade-offs
- Recursive CTEs for hierarchical data
- Materialized CTEs (PostgreSQL)

## CASE Expressions

```sql
SELECT
    category,
    COUNT(*) as total_products,
    COUNT(CASE WHEN price < 20 THEN 1 END) as budget_count,
    COUNT(CASE WHEN price BETWEEN 20 AND 100 THEN 1 END) as standard_count,
    COUNT(CASE WHEN price > 100 THEN 1 END) as premium_count,
    AVG(CASE WHEN in_stock = true THEN price END) as avg_available_price
FROM products
GROUP BY category;
```

See [case-expressions.md](references/case-expressions.md) for:
- Simple vs searched CASE
- Conditional aggregation patterns
- Pivot table simulation with CASE

## Cross-Database Compatibility

| Feature | PostgreSQL | MySQL | SQL Server |
|---------|-----------|-------|------------|
| String concat | `\|\|` | `CONCAT()` | `+` |
| Date add | `+ INTERVAL '7 days'` | `DATE_ADD(d, INTERVAL 7 DAY)` | `DATEADD(day, 7, d)` |
| Limit rows | `LIMIT N OFFSET M` | `LIMIT N OFFSET M` | `OFFSET M ROWS FETCH NEXT N ROWS ONLY` |
| Current date | `CURRENT_DATE` | `CURDATE()` | `GETDATE()` |

## Anti-Patterns to Avoid

| Avoid | Use Instead | Why |
|-------|-------------|-----|
| `SELECT *` | Explicit column list | Breaks code when schema changes |
| Implicit joins (`FROM a, b WHERE ...`) | Explicit `JOIN ON` | Hard to read, error-prone |
| Functions on indexed columns in WHERE | Sargable predicates | Can't use indexes |
| `NOT IN` with nullable columns | `NOT EXISTS` or `LEFT JOIN WHERE NULL` | NULL handling issues |
| `OR` in JOIN conditions | Separate queries with UNION | Poor performance |

## Performance Tips

- Use sargable predicates: `WHERE date >= '2024-01-01'` not `WHERE YEAR(date) = 2024`
- Avoid type casting in filters: `WHERE id = 123` not `WHERE id::text = '123'`
- Filter early, join late — reduce row count before expensive operations
- Use `EXISTS` over `IN` for correlated checks on large sets

source: PostgreSQL docs, MySQL docs, SQL Server docs, SQL standards
