# CASE Expressions

## Simple CASE Syntax

```sql
-- Basic categorization
SELECT 
    product_name,
    price,
    CASE 
        WHEN price < 10 THEN 'Budget'
        WHEN price < 50 THEN 'Standard'
        WHEN price < 100 THEN 'Premium'
        ELSE 'Luxury'
    END AS price_category,
    quantity
FROM products
ORDER BY price;

-- Specific value matching
SELECT 
    order_id,
    status,
    CASE status
        WHEN 'pending' THEN 'Awaiting Processing'
        WHEN 'processing' THEN 'Being Prepared'
        WHEN 'shipped' THEN 'In Transit'
        WHEN 'delivered' THEN 'Completed'
        WHEN 'cancelled' THEN 'Cancelled'
        ELSE 'Unknown Status'
    END AS status_display
FROM orders;
```

## CASE in SELECT

```sql
-- Multiple CASE expressions
SELECT 
    customer_name,
    country,
    total_purchases,
    order_count,
    -- Customer tier
    CASE 
        WHEN total_purchases > 50000 THEN 'Platinum'
        WHEN total_purchases > 10000 THEN 'Gold'
        WHEN total_purchases > 1000 THEN 'Silver'
        ELSE 'Standard'
    END AS tier,
    -- Region categorization
    CASE 
        WHEN country IN ('USA', 'Canada', 'Mexico') THEN 'North America'
        WHEN country IN ('UK', 'France', 'Germany', 'Italy', 'Spain') THEN 'Europe'
        WHEN country IN ('China', 'Japan', 'South Korea', 'India') THEN 'Asia'
        WHEN country IN ('Brazil', 'Argentina', 'Chile') THEN 'South America'
        ELSE 'Other'
    END AS region,
    -- Order frequency
    CASE 
        WHEN order_count >= 52 THEN 'Weekly'
        WHEN order_count >= 12 THEN 'Monthly'
        WHEN order_count >= 4 THEN 'Quarterly'
        ELSE 'Infrequent'
    END AS frequency
FROM customers
WHERE status = 'active';
```

## CASE in WHERE Clause

```sql
-- Dynamic filtering based on conditions
SELECT *
FROM products
WHERE 
    CASE 
        WHEN @filter_type = 'price' THEN price > @threshold
        WHEN @filter_type = 'quantity' THEN quantity > @threshold
        WHEN @filter_type = 'rating' THEN rating > @threshold
        ELSE TRUE
    END
ORDER BY product_name;

-- Department-specific rules
SELECT *
FROM employees
WHERE 
    CASE department
        WHEN 'Sales' THEN commission > 1000
        WHEN 'Engineering' THEN years_experience > 3
        WHEN 'Support' THEN customer_satisfaction > 4.5
        ELSE salary > 50000
    END;
```

## CASE in ORDER BY

```sql
-- Custom sort order
SELECT 
    product_name,
    category,
    stock_status
FROM products
ORDER BY 
    -- Sort by priority
    CASE stock_status
        WHEN 'out_of_stock' THEN 1
        WHEN 'low_stock' THEN 2
        WHEN 'in_stock' THEN 3
        WHEN 'overstock' THEN 4
        ELSE 5
    END,
    -- Then by category
    CASE category
        WHEN 'Featured' THEN 1
        WHEN 'New' THEN 2
        WHEN 'Sale' THEN 3
        ELSE 4
    END,
    product_name;

-- Dynamic sorting
SELECT *
FROM customers
ORDER BY 
    CASE @sort_column
        WHEN 'name' THEN customer_name
        WHEN 'email' THEN email
        WHEN 'created' THEN created_date::text
        ELSE customer_id::text
    END;
```

## CASE in Aggregations (Conditional Counting/Summing)

```sql
-- Conditional counting - "Pivot" style
SELECT 
    category,
    COUNT(*) AS total_products,
    -- Count by price range
    COUNT(CASE WHEN price < 20 THEN 1 END) AS budget_count,
    COUNT(CASE WHEN price BETWEEN 20 AND 50 THEN 1 END) AS standard_count,
    COUNT(CASE WHEN price BETWEEN 50 AND 100 THEN 1 END) AS premium_count,
    COUNT(CASE WHEN price > 100 THEN 1 END) AS luxury_count,
    -- Count by availability
    SUM(CASE WHEN in_stock THEN 1 ELSE 0 END) AS in_stock_count,
    SUM(CASE WHEN NOT in_stock THEN 1 ELSE 0 END) AS out_of_stock_count,
    -- Average of available items only
    AVG(CASE WHEN in_stock THEN price END) AS avg_available_price
FROM products
GROUP BY category
ORDER BY category;

-- Conditional summing by status
SELECT 
    DATE_TRUNC('day', order_date) AS day,
    COUNT(*) AS total_orders,
    -- Revenue by status
    SUM(CASE WHEN status = 'completed' THEN total_amount ELSE 0 END) AS completed_revenue,
    SUM(CASE WHEN status = 'pending' THEN total_amount ELSE 0 END) AS pending_revenue,
    SUM(CASE WHEN status = 'refunded' THEN total_amount ELSE 0 END) AS refunded_amount,
    -- Count by status
    COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed_count,
    COUNT(CASE WHEN status = 'refunded' THEN 1 END) AS refund_count,
    -- Refund rate
    ROUND(
        100.0 * COUNT(CASE WHEN status = 'refunded' THEN 1 END) / NULLIF(COUNT(*), 0),
        2
    ) AS refund_rate_pct
FROM orders
WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', order_date)
ORDER BY day;
```

## Pivot Tables with CASE

```sql
-- Transform rows to columns
SELECT 
    product_id,
    product_name,
    SUM(CASE WHEN month = 'January' THEN sales ELSE 0 END) AS jan_sales,
    SUM(CASE WHEN month = 'February' THEN sales ELSE 0 END) AS feb_sales,
    SUM(CASE WHEN month = 'March' THEN sales ELSE 0 END) AS mar_sales,
    SUM(CASE WHEN month = 'April' THEN sales ELSE 0 END) AS apr_sales,
    SUM(CASE WHEN month = 'May' THEN sales ELSE 0 END) AS may_sales,
    SUM(CASE WHEN month = 'June' THEN sales ELSE 0 END) AS jun_sales
FROM monthly_sales
WHERE year = 2024
GROUP BY product_id, product_name
ORDER BY product_name;

-- Year-over-year comparison
SELECT 
    category,
    SUM(CASE WHEN year = 2023 AND quarter = 'Q1' THEN revenue ELSE 0 END) AS "2023_Q1",
    SUM(CASE WHEN year = 2023 AND quarter = 'Q2' THEN revenue ELSE 0 END) AS "2023_Q2",
    SUM(CASE WHEN year = 2024 AND quarter = 'Q1' THEN revenue ELSE 0 END) AS "2024_Q1",
    SUM(CASE WHEN year = 2024 AND quarter = 'Q2' THEN revenue ELSE 0 END) AS "2024_Q2"
FROM quarterly_revenue
WHERE year IN (2023, 2024)
GROUP BY category
ORDER BY category;
```

## Data Cleaning with CASE

```sql
-- Standardize and clean data
SELECT 
    customer_id,
    -- Standardize country names
    CASE 
        WHEN TRIM(UPPER(country)) IN ('US', 'USA', 'UNITED STATES', 'U.S.', 'U.S.A.') 
            THEN 'United States'
        WHEN TRIM(UPPER(country)) IN ('UK', 'UNITED KINGDOM', 'GREAT BRITAIN', 'GB') 
            THEN 'United Kingdom'
        WHEN TRIM(UPPER(country)) IN ('', 'NULL', 'N/A', 'UNKNOWN')
            THEN 'Unknown'
        WHEN country IS NULL 
            THEN 'Unknown'
        ELSE INITCAP(TRIM(country))
    END AS standardized_country,
    -- Validate and clean email
    CASE 
        WHEN email IS NULL THEN 'no-email@missing.com'
        WHEN email NOT LIKE '%@%' THEN 'invalid-' || email
        WHEN email LIKE '%@%@%' THEN 'invalid-' || email
        ELSE LOWER(TRIM(email))
    END AS cleaned_email,
    -- Format phone number
    CASE 
        WHEN phone ~ '^\d{10}$' THEN  -- 10 digits
            '(' || SUBSTRING(phone, 1, 3) || ') ' ||
            SUBSTRING(phone, 4, 3) || '-' ||
            SUBSTRING(phone, 7, 4)
        WHEN phone IS NULL THEN 'No Phone'
        ELSE phone
    END AS formatted_phone,
    -- Categorize age groups
    CASE 
        WHEN age < 18 THEN 'Minor'
        WHEN age BETWEEN 18 AND 24 THEN '18-24'
        WHEN age BETWEEN 25 AND 34 THEN '25-34'
        WHEN age BETWEEN 35 AND 44 THEN '35-44'
        WHEN age BETWEEN 45 AND 54 THEN '45-54'
        WHEN age BETWEEN 55 AND 64 THEN '55-64'
        WHEN age >= 65 THEN '65+'
        ELSE 'Unknown'
    END AS age_group
FROM customer_raw_data;
```

## Nested CASE

```sql
-- CASE within CASE for complex logic
SELECT 
    product_name,
    price,
    quantity,
    CASE 
        WHEN quantity = 0 THEN 'Out of Stock'
        WHEN quantity < 10 THEN 
            CASE 
                WHEN price > 100 THEN 'Low Stock - High Value (Reorder Priority)'
                WHEN price > 50 THEN 'Low Stock - Medium Value'
                ELSE 'Low Stock - Low Value'
            END
        WHEN quantity < 50 THEN 'Adequate Stock'
        ELSE 'Overstocked'
    END AS stock_status
FROM products;
```

## CASE with NULL Handling

```sql
-- Explicit NULL handling in CASE
SELECT 
    customer_name,
    CASE 
        WHEN email IS NULL THEN 'No Email Provided'
        WHEN email = '' THEN 'Empty Email'
        WHEN email NOT LIKE '%@%' THEN 'Invalid Email Format'
        ELSE email
    END AS email_display,
    CASE 
        WHEN phone IS NOT NULL THEN phone
        WHEN mobile IS NOT NULL THEN mobile || ' (mobile)'
        WHEN alternate_contact IS NOT NULL THEN alternate_contact || ' (alt)'
        ELSE 'No Contact Information'
    END AS primary_contact
FROM customers;
```

## Performance Considerations

```sql
-- CASE evaluates sequentially - put most common cases first
SELECT 
    product_id,
    CASE 
        WHEN status = 'active' THEN 'Active'  -- 90% of rows
        WHEN status = 'discontinued' THEN 'Discontinued'  -- 8% of rows
        WHEN status = 'pending' THEN 'Pending'  -- 2% of rows
        ELSE 'Other'  -- Rare
    END AS status_label
FROM products;

-- Avoid expensive operations in CASE when possible
-- BAD (function called for every row):
SELECT 
    CASE 
        WHEN expensive_function(column) > 10 THEN 'High'
        ELSE 'Low'
    END
FROM large_table;

-- BETTER (calculate once in CTE):
WITH computed AS (
    SELECT 
        *,
        expensive_function(column) AS computed_value
    FROM large_table
)
SELECT 
    CASE 
        WHEN computed_value > 10 THEN 'High'
        ELSE 'Low'
    END
FROM computed;
```
