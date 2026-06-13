# Star Schema Design

## Star Schema Overview

A star schema consists of one or more **fact tables** (measurable events) surrounded by **dimension tables** (descriptive context). It is the foundation of dimensional modeling for data warehouses and analytics.

## Fact Table Types

### Transaction Fact Table

One row per business event. Most granular and most common.

```sql
-- Each row = one sale line item
CREATE TABLE fact_sales (
    sale_key         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key         INT NOT NULL REFERENCES dim_date(date_key),
    product_key      INT NOT NULL REFERENCES dim_product(product_key),
    customer_key     INT NOT NULL REFERENCES dim_customer(customer_key),
    store_key        INT NOT NULL REFERENCES dim_store(store_key),
    promotion_key    INT NOT NULL REFERENCES dim_promotion(promotion_key),
    -- Degenerate dimension (no separate dim table needed)
    transaction_id   VARCHAR(20) NOT NULL,
    -- Measures (always numeric, additive where possible)
    quantity_sold    INT NOT NULL,
    unit_price       NUMERIC(10,2) NOT NULL,
    discount_amount  NUMERIC(10,2) NOT NULL DEFAULT 0,
    net_amount       NUMERIC(12,2) NOT NULL,
    cost_amount      NUMERIC(12,2) NOT NULL,
    profit_amount    NUMERIC(12,2) NOT NULL
);

CREATE INDEX idx_fact_sales_date ON fact_sales(date_key);
CREATE INDEX idx_fact_sales_product ON fact_sales(product_key);
CREATE INDEX idx_fact_sales_customer ON fact_sales(customer_key);
```

### Periodic Snapshot Fact Table

One row per entity per time period. Captures cumulative state.

```sql
-- Monthly account balance snapshot
CREATE TABLE fact_account_monthly_snapshot (
    date_key             INT NOT NULL REFERENCES dim_date(date_key),
    account_key          INT NOT NULL REFERENCES dim_account(account_key),
    account_type_key     INT NOT NULL REFERENCES dim_account_type(account_type_key),
    -- Semi-additive measures (can sum across non-time dimensions)
    opening_balance      NUMERIC(14,2) NOT NULL,
    closing_balance      NUMERIC(14,2) NOT NULL,
    -- Fully additive measures
    total_deposits       NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_withdrawals    NUMERIC(14,2) NOT NULL DEFAULT 0,
    transaction_count    INT NOT NULL DEFAULT 0,
    PRIMARY KEY (date_key, account_key)
);
```

### Accumulating Snapshot Fact Table

One row per process instance, updated as milestones are reached.

```sql
-- Order fulfillment pipeline tracking
CREATE TABLE fact_order_fulfillment (
    order_key               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id                VARCHAR(20) NOT NULL UNIQUE,
    -- Multiple date keys track pipeline milestones
    order_date_key          INT NOT NULL REFERENCES dim_date(date_key),
    payment_date_key        INT REFERENCES dim_date(date_key),
    ship_date_key           INT REFERENCES dim_date(date_key),
    delivery_date_key       INT REFERENCES dim_date(date_key),
    return_date_key         INT REFERENCES dim_date(date_key),
    -- Dimension keys
    customer_key            INT NOT NULL REFERENCES dim_customer(customer_key),
    product_key             INT NOT NULL REFERENCES dim_product(product_key),
    -- Lag measures (days between milestones)
    days_to_payment         INT,
    days_to_ship            INT,
    days_to_deliver         INT,
    -- Amount measures
    order_amount            NUMERIC(12,2) NOT NULL,
    shipping_cost           NUMERIC(10,2)
);

-- Update as milestones are reached
UPDATE fact_order_fulfillment
SET ship_date_key = 20240320,
    days_to_ship = 20240320 - order_date_key
WHERE order_id = 'ORD-2024-78901';
```

## Dimension Table Design

### Standard Dimension

```sql
-- Rich descriptive attributes for slicing and dicing
CREATE TABLE dim_product (
    product_key       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Natural key from source system
    product_id        VARCHAR(20) NOT NULL,
    -- Descriptive attributes (hierarchies for drill-down)
    product_name      VARCHAR(200) NOT NULL,
    brand             VARCHAR(100),
    category          VARCHAR(100) NOT NULL,
    subcategory       VARCHAR(100),
    department        VARCHAR(100) NOT NULL,
    -- Physical attributes
    weight_kg         NUMERIC(8,3),
    package_size      VARCHAR(50),
    -- Pricing tier (for analysis grouping)
    price_tier        VARCHAR(20),
    -- SCD Type 2 tracking columns
    effective_date    DATE NOT NULL,
    expiration_date   DATE NOT NULL DEFAULT '9999-12-31',
    is_current        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_dim_product_natural ON dim_product(product_id);
CREATE INDEX idx_dim_product_current ON dim_product(product_id) WHERE is_current = TRUE;
```

### Date Dimension

```sql
-- Pre-populated calendar table (essential for any star schema)
CREATE TABLE dim_date (
    date_key          INT PRIMARY KEY,           -- YYYYMMDD format
    full_date         DATE NOT NULL UNIQUE,
    day_of_week       INT NOT NULL,              -- 1=Monday, 7=Sunday
    day_name          VARCHAR(10) NOT NULL,       -- Monday, Tuesday...
    day_of_month      INT NOT NULL,
    day_of_year       INT NOT NULL,
    week_of_year      INT NOT NULL,
    month_number      INT NOT NULL,
    month_name        VARCHAR(10) NOT NULL,
    month_short       CHAR(3) NOT NULL,           -- Jan, Feb...
    quarter           INT NOT NULL,
    quarter_name      CHAR(2) NOT NULL,           -- Q1, Q2, Q3, Q4
    year              INT NOT NULL,
    fiscal_year       INT NOT NULL,
    fiscal_quarter    INT NOT NULL,
    is_weekend        BOOLEAN NOT NULL,
    is_holiday        BOOLEAN NOT NULL DEFAULT FALSE,
    holiday_name      VARCHAR(100)
);

-- Generate date dimension rows (PostgreSQL)
INSERT INTO dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT AS date_key,
    d AS full_date,
    EXTRACT(ISODOW FROM d)::INT AS day_of_week,
    TO_CHAR(d, 'Day') AS day_name,
    EXTRACT(DAY FROM d)::INT AS day_of_month,
    EXTRACT(DOY FROM d)::INT AS day_of_year,
    EXTRACT(WEEK FROM d)::INT AS week_of_year,
    EXTRACT(MONTH FROM d)::INT AS month_number,
    TO_CHAR(d, 'Month') AS month_name,
    TO_CHAR(d, 'Mon') AS month_short,
    EXTRACT(QUARTER FROM d)::INT AS quarter,
    'Q' || EXTRACT(QUARTER FROM d)::TEXT AS quarter_name,
    EXTRACT(YEAR FROM d)::INT AS year,
    CASE WHEN EXTRACT(MONTH FROM d) >= 7
         THEN EXTRACT(YEAR FROM d)::INT + 1
         ELSE EXTRACT(YEAR FROM d)::INT
    END AS fiscal_year,
    CASE WHEN EXTRACT(MONTH FROM d) >= 7
         THEN EXTRACT(QUARTER FROM DATE_TRUNC('month', d) - INTERVAL '6 months')::INT
         ELSE EXTRACT(QUARTER FROM DATE_TRUNC('month', d) + INTERVAL '6 months')::INT
    END AS fiscal_quarter,
    EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend,
    FALSE AS is_holiday,
    NULL AS holiday_name
FROM generate_series('2020-01-01'::date, '2030-12-31'::date, '1 day'::interval) d;
```

### Junk Dimension

Collects low-cardinality flags and indicators that do not warrant their own dimension.

```sql
-- Instead of cluttering the fact table with boolean flags
CREATE TABLE dim_order_flags (
    order_flag_key   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    is_gift_wrapped  BOOLEAN NOT NULL,
    is_expedited     BOOLEAN NOT NULL,
    is_tax_exempt    BOOLEAN NOT NULL,
    payment_method   VARCHAR(20) NOT NULL,
    order_channel    VARCHAR(20) NOT NULL
);

-- Pre-populate all meaningful combinations
INSERT INTO dim_order_flags (is_gift_wrapped, is_expedited, is_tax_exempt, payment_method, order_channel)
SELECT DISTINCT
    gw, ex, te, pm, ch
FROM
    (VALUES (TRUE), (FALSE)) AS t1(gw),
    (VALUES (TRUE), (FALSE)) AS t2(ex),
    (VALUES (TRUE), (FALSE)) AS t3(te),
    (VALUES ('credit_card'), ('debit_card'), ('paypal'), ('wire')) AS t4(pm),
    (VALUES ('web'), ('mobile'), ('store'), ('phone')) AS t5(ch);
```

## Surrogate Keys

```sql
-- Always use surrogate (system-generated) keys in dimension tables
-- Natural keys go into a separate column for traceability

-- GOOD: surrogate key + natural key
CREATE TABLE dim_customer (
    customer_key    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL,   -- natural key from source
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(255),
    segment         VARCHAR(50),
    effective_date  DATE NOT NULL,
    expiration_date DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

-- BAD: using natural key as PK in dimension
-- CREATE TABLE dim_customer (
--     customer_id  VARCHAR(20) PRIMARY KEY,  -- changes, varying length, poor join perf
--     ...
-- );
```

**Why surrogate keys**:
- Natural keys can change (email, SSN, product code)
- Integer joins are faster than string joins
- Required for SCD Type 2 (multiple rows per natural key)
- Insulates the warehouse from source system key changes

## Conformed Dimensions

Dimensions shared across multiple fact tables with identical meaning.

```sql
-- dim_customer is conformed: used by fact_sales, fact_returns, fact_support_tickets
-- SAME customer_key means SAME customer across all fact tables

-- fact_sales
CREATE TABLE fact_sales (
    sale_key      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_key  INT NOT NULL REFERENCES dim_customer(customer_key),
    -- ...
);

-- fact_returns
CREATE TABLE fact_returns (
    return_key    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_key  INT NOT NULL REFERENCES dim_customer(customer_key),
    -- ...
);

-- Enables cross-process analysis
SELECT
    dc.segment,
    COUNT(DISTINCT fs.sale_key) AS total_sales,
    COUNT(DISTINCT fr.return_key) AS total_returns,
    ROUND(COUNT(DISTINCT fr.return_key)::NUMERIC / NULLIF(COUNT(DISTINCT fs.sale_key), 0) * 100, 2) AS return_rate_pct
FROM dim_customer dc
LEFT JOIN fact_sales fs ON dc.customer_key = fs.customer_key
LEFT JOIN fact_returns fr ON dc.customer_key = fr.customer_key
WHERE dc.is_current = TRUE
GROUP BY dc.segment;
```

## Measure Types

| Type | Description | Can Sum Across Time? | Example |
|------|-------------|---------------------|---------|
| **Additive** | Can be summed across all dimensions | Yes | Revenue, quantity, cost |
| **Semi-additive** | Can be summed across non-time dimensions | No (use AVG or snapshot) | Account balance, inventory level |
| **Non-additive** | Cannot be summed meaningfully | No | Ratios, percentages, unit price |

```sql
-- Querying semi-additive measures correctly
-- WRONG: SUM of balances across months makes no sense
-- SELECT SUM(closing_balance) FROM fact_account_monthly_snapshot;

-- CORRECT: Get latest balance per account, then sum
SELECT
    dat.account_type_key,
    SUM(f.closing_balance) AS total_balance
FROM fact_account_monthly_snapshot f
INNER JOIN dim_account_type dat ON f.account_type_key = dat.account_type_key
WHERE f.date_key = (SELECT MAX(date_key) FROM fact_account_monthly_snapshot)
GROUP BY dat.account_type_key;
```

## Star Schema Query Pattern

```sql
-- Typical star schema query: aggregate facts, filter/group by dimensions
SELECT
    dd.year,
    dd.quarter_name,
    dp.category,
    dp.brand,
    ds.region,
    SUM(fs.quantity_sold) AS total_units,
    SUM(fs.net_amount) AS total_revenue,
    SUM(fs.profit_amount) AS total_profit,
    ROUND(SUM(fs.profit_amount) / NULLIF(SUM(fs.net_amount), 0) * 100, 2) AS profit_margin_pct
FROM fact_sales fs
INNER JOIN dim_date dd ON fs.date_key = dd.date_key
INNER JOIN dim_product dp ON fs.product_key = dp.product_key
INNER JOIN dim_store ds ON fs.store_key = ds.store_key
WHERE dd.year = 2024
  AND dp.department = 'Electronics'
GROUP BY dd.year, dd.quarter_name, dp.category, dp.brand, ds.region
ORDER BY total_revenue DESC;
```

## Star vs Snowflake Schema

```sql
-- STAR: dimension table is denormalized (flat)
-- dim_product has category, subcategory, department all in one table
-- Fewer joins, simpler queries, preferred for most analytics

-- SNOWFLAKE: dimension table is normalized (hierarchies broken out)
CREATE TABLE dim_department (
    department_key  INT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_category (
    category_key    INT PRIMARY KEY,
    category_name   VARCHAR(100) NOT NULL,
    department_key  INT NOT NULL REFERENCES dim_department(department_key)
);

CREATE TABLE dim_product_snowflake (
    product_key     INT PRIMARY KEY,
    product_name    VARCHAR(200) NOT NULL,
    category_key    INT NOT NULL REFERENCES dim_category(category_key)
);
-- More joins needed for queries, but less storage and strict hierarchy enforcement
-- Generally avoid snowflaking unless dimension tables are extremely large
```
