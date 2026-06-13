# WHERE Clause Patterns

## Basic Comparison Operators

```sql
-- Equality and inequality
WHERE age = 25
WHERE status != 'cancelled'  -- or <> 'cancelled'
WHERE price > 100
WHERE quantity <= 50
WHERE created_date >= '2024-01-01'

-- Combining with AND/OR
WHERE age >= 18 AND age < 65
WHERE country = 'USA' OR country = 'Canada'

-- Operator precedence: AND before OR
WHERE status = 'active' OR status = 'pending' AND country = 'USA'
-- Evaluated as: status = 'active' OR (status = 'pending' AND country = 'USA')

-- Use parentheses for clarity
WHERE (status = 'active' OR status = 'pending') AND country = 'USA'
```

## IN and NOT IN

```sql
-- IN clause (cleaner than multiple ORs)
WHERE country IN ('USA', 'Canada', 'Mexico')
WHERE status IN ('active', 'pending', 'approved')

-- More readable than:
WHERE country = 'USA' OR country = 'Canada' OR country = 'Mexico'

-- IN with subquery
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE order_date >= '2024-01-01'
)

-- NOT IN with NULL caveat
WHERE category NOT IN ('A', 'B', NULL)  -- Returns NO rows if NULL in list!

-- Safe NOT IN pattern
WHERE category NOT IN (
    SELECT category 
    FROM excluded_categories 
    WHERE category IS NOT NULL
)
-- Or use NOT EXISTS:
WHERE NOT EXISTS (
    SELECT 1 FROM excluded_categories e WHERE e.category = products.category
)
```

## BETWEEN for Ranges

```sql
-- Inclusive range (includes both boundaries)
WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31'
WHERE age BETWEEN 18 AND 65
WHERE price BETWEEN 10.00 AND 100.00

-- Equivalent to:
WHERE order_date >= '2024-01-01' AND order_date <= '2024-12-31'

-- NOT BETWEEN
WHERE age NOT BETWEEN 0 AND 17  -- 18 and older

-- Date range gotcha with timestamps
WHERE created_at BETWEEN '2024-01-01' AND '2024-01-31'
-- Includes 2024-01-31 00:00:00 but NOT 2024-01-31 23:59:59!

-- Better for full day inclusion:
WHERE created_at >= '2024-01-01' 
  AND created_at < '2024-02-01'  -- Exclusive upper bound
```

## LIKE Pattern Matching

```sql
-- Wildcards: % (any characters), _ (single character)

-- Starts with
WHERE name LIKE 'John%'
WHERE email LIKE 'admin%'

-- Ends with
WHERE email LIKE '%@gmail.com'
WHERE filename LIKE '%.pdf'

-- Contains
WHERE description LIKE '%urgent%'
WHERE address LIKE '%Main Street%'

-- Exact positions
WHERE phone LIKE '555-____'  -- Four digits after 555-
WHERE code LIKE 'A__B'  -- A, two any chars, B

-- NOT LIKE
WHERE email NOT LIKE '%@spam.com'

-- Case sensitivity (database-dependent)
WHERE name LIKE 'john%'  -- Case-insensitive in MySQL by default
WHERE name ILIKE 'john%'  -- Case-insensitive in PostgreSQL
WHERE LOWER(name) LIKE 'john%'  -- Explicit case-insensitive (any database)

-- PostgreSQL regular expressions
WHERE text ~ '^[A-Z]'  -- Starts with uppercase letter
WHERE email ~* '.*@gmail\.com$'  -- Case-insensitive regex
```

## NULL Handling

```sql
-- Check for NULL
WHERE phone_number IS NULL
WHERE email IS NOT NULL

-- NULL comparisons (common mistake)
WHERE column_name = NULL  -- WRONG - always FALSE!
WHERE column_name IS NULL  -- CORRECT

-- NULL in logical operations
WHERE active = TRUE OR active IS NULL  -- Includes NULLs
WHERE NOT (inactive = TRUE)  -- Does NOT include NULLs
WHERE inactive IS NOT TRUE  -- Includes NULLs and FALSE

-- COALESCE for NULL handling
WHERE COALESCE(phone, mobile, 'N/A') != 'N/A'
WHERE COALESCE(discount_rate, 0) > 0

-- NULL-safe equality (MySQL specific)
WHERE column1 <=> column2  -- True if both NULL
```

## Sargable vs Non-Sargable Predicates

Sargable (Search ARGument ABLE) = can use indexes efficiently

```sql
-- SARGABLE (GOOD - can use indexes)
WHERE customer_id = 12345
WHERE created_date >= '2024-01-01'
WHERE status IN ('active', 'pending')
WHERE email LIKE 'admin%'  -- Prefix only

-- NON-SARGABLE (BAD - can't use indexes)
WHERE YEAR(created_date) = 2024  -- Function on column
WHERE LOWER(email) = 'user@example.com'  -- Function on column
WHERE salary * 1.1 > 50000  -- Calculation on column
WHERE email LIKE '%@gmail.com'  -- Leading wildcard

-- How to fix:

-- BAD
WHERE YEAR(order_date) = 2024
-- GOOD
WHERE order_date >= '2024-01-01' AND order_date < '2025-01-01'

-- BAD
WHERE price * quantity > 1000
-- GOOD
WHERE price > 1000 / NULLIF(quantity, 0)

-- BAD  
WHERE SUBSTRING(code, 1, 3) = 'ABC'
-- GOOD
WHERE code LIKE 'ABC%'
```

## Date and Time Filtering

```sql
-- Date comparisons
WHERE order_date = '2024-01-15'
WHERE created_at >= CURRENT_DATE
WHERE updated_at < NOW()

-- Date ranges
WHERE order_date >= '2024-01-01' AND order_date < '2024-02-01'

-- Relative dates
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'  -- PostgreSQL
WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)  -- MySQL
WHERE created_at >= DATEADD(day, -30, GETDATE())  -- SQL Server

-- Extract date parts (not sargable)
WHERE EXTRACT(YEAR FROM order_date) = 2024  -- Can't use index

-- Better (sargable)
WHERE order_date >= '2024-01-01' AND order_date < '2025-01-01'

-- Time of day
WHERE EXTRACT(HOUR FROM event_time) BETWEEN 9 AND 17  -- Not sargable
-- Better:
WHERE event_time::time BETWEEN '09:00' AND '17:00'
```

## Complex Conditions

```sql
-- Multiple ranges
WHERE (age BETWEEN 18 AND 25) 
   OR (age BETWEEN 35 AND 45)
   OR (age >= 65)

-- Subquery in WHERE
WHERE total_amount > (
    SELECT AVG(total_amount) 
    FROM orders 
    WHERE EXTRACT(YEAR FROM order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
)

-- Dynamic filtering
WHERE 
    (@filter_by_price IS NULL OR price >= @min_price)
    AND (@filter_by_category IS NULL OR category = @category)
    AND (@filter_by_stock IS NULL OR in_stock = @in_stock)
```

## Performance Tips

```sql
-- Put most selective filters first (optimizer usually handles this)
WHERE user_id = 12345  -- Very selective
  AND status = 'active'  -- Less selective
  AND country = 'USA'  -- Even less selective

-- Use EXISTS instead of IN for large result sets
-- Slower:
WHERE customer_id IN (
    SELECT customer_id FROM large_table WHERE complex_condition
)

-- Faster (stops at first match):
WHERE EXISTS (
    SELECT 1 FROM large_table 
    WHERE large_table.customer_id = main.customer_id 
      AND complex_condition
)
```
